"""Run the parity manifest on one engine, one case at a time, and record what happened.

Each run appends one JSON line to `results-<machine>.jsonl`. A rerun skips a case only
when the same campaign already succeeded on it, so a broken link costs only the cases not
yet done, and a changed commit costs every case.

A campaign is pinned by `<work>/campaign-<machine>.json`: the commit, the platform, the
interpreter and the asset digests. A case carries the fingerprint of that manifest and its
own payload, so a result from another revision cannot pass for a result of this one, and
`report.py` can show which two figures were never comparable.

The `$file` and `$field` markers in a payload are resolved here, from the asset directory,
and each byte is checked against `assets.sha256`, so both engines send the same bytes.

The `$file` check is the reason `build_assets.py` runs once. Building it again makes
different bytes, and a case that cites them is not the same case.
"""

import argparse
import base64
import contextlib
import hashlib
import http.client
import json
import math
import os
import platform
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# How often the memory sampler reads the host, in seconds.
SAMPLE_SECONDS = 0.2
# How long to wait between two reads of a running operation's status.
POLL_SECONDS = 1.0
# The longest a status read or a result download may take. Neither may outlive the
# case's own deadline, and a result that lands on the deadline still gets a minute.
FETCH_SECONDS = 600.0
FETCH_FLOOR_SECONDS = 60.0
POLL_LONGEST_SECONDS = 180.0
# The only manifest fields a reuse may waive: they cannot change a measured figure.
REUSABLE_FIELDS = {"dirty", "changes", "python"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def media_bytes(body: bytes, kind: str) -> bytes:
    """The artifact itself. An image crosses as JSON with the PNG inside it; every other
    kind crosses as the file."""
    if kind != "image" or body[:1] != b"{":
        return body
    return base64.b64decode(json.loads(body)["images"][0]["png_base64"])


def png_facts(media: bytes) -> dict:
    """Width and height from a whole PNG, not from four bytes that might be one.

    A truncated download still succeeds at the API. The end marker is what tells a whole
    file from the first chunk of one.
    """
    if media[:8] != b"\x89PNG\r\n\x1a\n" or media[12:16] != b"IHDR" or media[-8:-4] != b"IEND":
        return {}
    return {"width": int.from_bytes(media[16:20], "big"), "height": int.from_bytes(media[20:24], "big")}


def wav_facts(media: bytes) -> dict:
    """Rate, channels and seconds from the RIFF chunks themselves.

    A search for `data` finds the word in any metadata block before it, and a float file
    has a wider format block. Walking the chunks reads the header the file means.
    """
    if media[:4] != b"RIFF" or media[8:12] != b"WAVE":
        return {}
    facts = {}
    frames = None
    position = 12
    while position + 8 <= len(media):
        name = media[position : position + 4]
        size = int.from_bytes(media[position + 4 : position + 8], "little")
        start = position + 8
        if name == b"fmt " and size >= 16 and start + 16 <= len(media):
            facts["channels"] = int.from_bytes(media[start + 2 : start + 4], "little")
            facts["sample_rate"] = int.from_bytes(media[start + 4 : start + 8], "little")
            facts["_width"] = int.from_bytes(media[start + 14 : start + 16], "little")
        elif name == b"data":
            # A declared size the file does not hold is a truncated download, and the
            # seconds it claims are not seconds the machine produced.
            frames = size if start + size <= len(media) else 0
            break
        position = start + size + (size & 1)
    if frames is None or "_width" not in facts:
        return {}
    width = facts.pop("_width")
    stride = facts["sample_rate"] * facts["channels"] * width // 8
    facts["seconds"] = round(frames / stride, 2) if stride else 0
    return facts


def mp4_boxes(media: bytes, start: int, end: int):
    """The boxes in one range, as (kind, first byte of the body, end of the box).

    A size below the header, or one past the range, ends the walk: a truncated file says
    nothing about the tracks it meant to hold.
    """
    position = start
    while position + 8 <= end:
        size = int.from_bytes(media[position : position + 4], "big")
        kind = media[position + 4 : position + 8]
        header = 8
        if size == 1:
            if position + 16 > end:
                return
            size = int.from_bytes(media[position + 8 : position + 16], "big")
            header = 16
        elif size == 0:
            size = end - position
        if size < header or position + size > end:
            return
        yield kind, position + header, position + size
        position += size


MP4_CONTAINERS = (b"moov", b"trak", b"mdia")


def mp4_audio_track(media: bytes, start: int = 0, end: int | None = None, depth: int = 0) -> bool:
    """Whether a track names an audio handler, read from the box structure.

    A search for `soun` anywhere in the file finds it in metadata, in a thumbnail or in a
    payload, and says yes to a video with no sound at all.
    """
    if end is None:
        end = len(media)
    if depth > 3:
        return False
    for kind, body_start, body_end in mp4_boxes(media, start, end):
        if kind == b"hdlr" and media[body_start + 8 : body_start + 12] == b"soun":
            return True
        if kind in MP4_CONTAINERS and mp4_audio_track(media, body_start, body_end, depth + 1):
            return True
    return False


def output_facts(body: bytes, kind: str) -> dict:
    """What the bytes say about themselves.

    A status of succeeded proves that the API answered, and nothing about the answer. A
    video that lost its audio track still succeeds. These facts are cheap, they need no
    dependency, and they make the two machines comparable before the times are.
    """
    media = media_bytes(body, kind)
    facts = {"sha256": sha256(media), "bytes": len(media)}
    if kind == "image":
        facts.update(png_facts(media))
    elif kind in ("voice", "music"):
        facts.update(wav_facts(media))
    elif kind == "video":
        facts["audio_track"] = mp4_audio_track(media)
    return facts


def slug(name: str) -> str:
    """A name a file system accepts, keeping the readable part of a case id."""
    return "".join(character if character.isalnum() or character in "._-" else "_" for character in name)


def load_assets(work: Path) -> dict[str, str]:
    """The digests `build_assets.py` wrote, when the campaign has assets.

    A case that cites a file is checked where it is resolved, so a campaign of generated
    cases needs no asset directory and a case that names one cannot skip the check.
    """
    path = work / "assets.sha256"
    if not path.is_file():
        return {}
    digests = {}
    for line in path.read_text().splitlines():
        if line.strip():
            digest, _, name = line.partition("  ")
            digests[name] = digest
    return digests


def resolve(value, assets: Path, digests: dict[str, str]):
    if isinstance(value, list):
        return [resolve(item, assets, digests) for item in value]
    if isinstance(value, dict):
        if "$file" in value:
            name = value["$file"]
            data = (assets / name).read_bytes()
            expected = digests.get(name)
            if expected is None:
                raise SystemExit(
                    f"{name} has no digest in assets.sha256. Build the assets on one machine and copy "
                    "the directory here. A second build makes different bytes, and a case that cites "
                    "them is not the same case."
                )
            if sha256(data) != expected:
                raise SystemExit(f"{name} does not match assets.sha256. Both machines must read the same bytes.")
            encoded = base64.b64encode(data).decode("ascii")
            field = value.get("$field")
            return encoded if field is None else {field: encoded}
        return {key: resolve(item, assets, digests) for key, item in value.items()}
    return value


def call(base: str, path: str, body: dict | None = None, method: str = "GET", timeout: float = 120):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path, data=data, headers={"Content-Type": "application/json"}, method=method
    )
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return json.loads(answer.read() or b"null")


def memory_free_gib() -> float:
    """Free memory on a Linux host. A macOS host reports 0, and the row carries no figure."""
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1048576
    except FileNotFoundError:
        return 0.0
    return 0.0


class MemorySampler(threading.Thread):
    """Read free memory while one case runs.

    The lowest sample is the figure the reference page prints. A model that allocates and
    frees inside one job shows nothing at the two ends of it, so the ends are not a peak.
    """

    def __init__(self, interval: float = SAMPLE_SECONDS):
        super().__init__(daemon=True)
        self._interval = interval
        self._stopped = threading.Event()
        self.start_gib = memory_free_gib()
        self.min_gib = self.start_gib
        self.samples = 0

    def run(self) -> None:
        while not self._stopped.wait(self._interval):
            free = memory_free_gib()
            if free:
                self.min_gib = min(self.min_gib, free)
            self.samples += 1

    def finish(self) -> dict:
        self._stopped.set()
        self.join()
        if not self.start_gib:
            return {}
        return {
            "free_start_gib": round(self.start_gib, 2),
            "free_min_gib": round(self.min_gib, 2),
            "free_end_gib": round(memory_free_gib(), 2),
            "peak_drop_gib": round(self.start_gib - self.min_gib, 2),
            "samples": self.samples,
        }


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown"


def git_changes() -> str | None:
    """A digest of what the working tree changes, so two dirty trees are told apart.

    A boolean says a result came from an uncommitted tree; it does not say which. The
    digest covers the diff and every untracked file's name and bytes.
    """
    try:
        diff = subprocess.run(["git", "diff", "HEAD"], capture_output=True, check=True, timeout=20).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    digest = hashlib.sha256(diff.encode() if isinstance(diff, str) else diff)
    for name in sorted(untracked):
        digest.update(name.encode())
        with contextlib.suppress(OSError):
            digest.update(Path(name).read_bytes())
    return digest.hexdigest()[:16]


def git_dirty() -> bool | str:
    """Whether the tree under test carries changes its commit does not name.

    A result from a modified tree belongs to a revision nobody can check out.
    """
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown"
    return bool(status.stdout.strip())


WORKSPACE_ROUTES = {"image": "images", "video": "videos", "voice": "voice", "music": "music"}


def live_configuration(state: dict, capabilities) -> dict:
    """What the running studio can prove about itself, with the parts that move dropped.

    The active selection is left out: it moves as a campaign runs, and every case names its
    own backend. A fingerprint that held it would refuse a campaign its own resume. Each
    offered backend's capabilities take its place, because they carry the sizes a model
    accepts and the precision its weights were built at, which a model id does not. The
    resident list is left out too, since it changes with every job.
    """
    studio = json.loads(json.dumps(state.get("studio") or {}))
    memory = studio.pop("memory", None) or {}
    offered = {}
    for workspace, section in studio.items():
        if not isinstance(section, dict) or "backends" not in section:
            continue
        section.pop("active", None)
        section.pop("capabilities", None)
        for backend in section["backends"]:
            backend_id = backend["id"] if isinstance(backend, dict) else backend
            offered[f"{workspace}/{backend_id}"] = capabilities(workspace, backend_id)
    return {
        "studio": studio,
        "offered": offered,
        "memory_policy": memory.get("policy"),
        "memory_boundary_gib": memory.get("boundary_gib"),
    }


def engine_pins() -> dict[str, str]:
    """Every pinned engine script, and the studio's own dependency lock.

    A child script's PEP 723 header pins the packages that engine runs with, so the
    script's digest is that engine's lock. `uv.lock` holds the studio's own. A trial that
    ran under different pins is a different trial, and the campaign identity refuses to
    compare across the change.
    """
    root = Path(__file__).resolve().parents[2]
    pins = {
        str(path.relative_to(root)): sha256(path.read_bytes())
        for path in sorted(root.glob("studio/l3_interface_adapters/gateways/**/*_child.py"))
    }
    lock = root / "uv.lock"
    if lock.is_file():
        pins["uv.lock"] = sha256(lock.read_bytes())
    return pins


def campaign_manifest(machine: str, digests: dict[str, str], live: dict | None = None) -> dict:
    """Everything a result depends on that is not the payload itself."""
    return {
        "machine": machine,
        "git": git_sha(),
        "dirty": git_dirty(),
        "changes": git_changes(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "assets": digests,
        "pins": engine_pins(),
        "studio": live or {},
    }


def fingerprint(case: dict, manifest: dict) -> str:
    return sha256(json.dumps({"manifest": manifest, "case": case}, sort_keys=True).encode())[:16]


def repair_tail(path: Path) -> None:
    """Drop an interrupted last line before anything is appended after it.

    `rows()` skips a damaged last line, but appending a record after it joins the two and
    the result is unreadable. The repair runs once, before the first append of a run.
    """
    if not path.is_file():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    cut = data.rfind(b"\n") + 1
    path.write_bytes(data[:cut])
    print(f"  {path.name}: dropped {len(data) - cut} bytes of an interrupted line", flush=True)


def rows(path: Path) -> list[dict]:
    """Every record in a JSONL file, or every record but an interrupted last line.

    The runner appends one line per trial, so a process that dies mid-append leaves half
    a line. Refusing the whole file would throw away every completed row with it, which is
    what the resume is for. Only the final line is forgiven: a bad line anywhere else is
    corruption, and it has to be seen.
    """
    if not path.is_file():
        return []
    lines = path.read_text().splitlines()
    records = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                print(f"  {path.name}: the last line is incomplete, so it is ignored", flush=True)
                break
            raise SystemExit(f"{path.name} line {index + 1} is not a record: {line[:80]}") from None
    return records


def records(path: Path) -> dict[str, dict]:
    """Every record in the file, with the last line for a case winning."""
    picked = {}
    for record in rows(path):
        picked[record["id"]] = record
    return picked


def saved(work: Path, record: dict) -> bool:
    """Whether the artifact this row names is still the bytes it hashed.

    An image crosses as JSON with the PNG inside it, so the hash in the row is the hash
    of the decoded picture. Both forms are accepted for a row written before the kind
    was recorded.
    """
    relative = record.get("file")
    expected = record.get("sha256")
    if not relative or expected is None:
        return False
    path = work / relative
    if not path.is_file():
        return False
    body = path.read_bytes()
    return expected in (sha256(body), sha256(media_bytes(body, record.get("kind", "image"))))


def done(path: Path, fingerprints: dict[str, str], work: Path) -> set[str]:
    """The cases this campaign already finished, and only those.

    A row is a claim. The file it names is the evidence, and a campaign copied between
    machines can carry one without the other: a lost or truncated artifact would
    otherwise count as a finished case that nobody can look at.
    """
    return {
        case_id
        for case_id, record in records(path).items()
        if record.get("status") == "succeeded"
        and record.get("fingerprint") == fingerprints.get(case_id)
        and saved(work, record)
    }


def checkpoint_path(work: Path, machine: str, case_id: str, out: Path | None = None) -> Path:
    """One file per case and per results file, and two ids that read alike after slugging
    are still two files.

    A warm pass repeats cold cases into its own results file, with the same ids and the
    same fingerprints. Sharing one checkpoint made it resume the cold pass's operation: a
    0 s timeout when that operation was older than the deadline, and the cold run's figures
    under the warm row when it was not. The default results file keeps its old folder, so a
    campaign that is already running still resumes.
    """
    folder = f"phases-{machine}"
    if out is not None and out.name != f"results-{machine}.jsonl":
        folder = f"{folder}-{out.stem}"
    directory = work / folder
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{slug(case_id)}-{sha256(case_id.encode())[:12]}.json"


def read_checkpoint(path: Path, expected: str) -> dict:
    if not path.is_file():
        return {}
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError:
        # A damaged file costs the case a second run, not the campaign.
        print(f"  {path.name} is not a checkpoint, so the case runs again", flush=True)
        return {}
    return record if record.get("fingerprint") == expected else {}


def write_checkpoint(path: Path, record: dict) -> None:
    """Write whole, then move into place, so a crash leaves no half file."""
    scratch = path.with_suffix(".tmp")
    scratch.write_text(json.dumps(record))
    scratch.replace(path)


class OperationGone(Exception):
    """The studio no longer holds this operation, so its record cannot be trusted."""


def remaining(deadline: float, since: float) -> float | None:
    """The seconds left of one case's budget, or None when the caller set no limit."""
    return None if not deadline else deadline - (time.time() - since)


def poll_timeout(deadline: float, accepted_at: float) -> float:
    """A status read may not outlive the deadline it is checking against."""
    left = remaining(deadline, accepted_at)
    return POLL_LONGEST_SECONDS if left is None else max(1.0, min(POLL_LONGEST_SECONDS, left))


def fetch_timeout(deadline: float, accepted_at: float) -> float:
    """A download gets the rest of the budget, but never less than a minute.

    A render that lands on the deadline still has a result to collect, and a stalled
    download has to end soon after the budget does.
    """
    left = remaining(deadline, accepted_at)
    return FETCH_SECONDS if left is None else min(FETCH_SECONDS, max(FETCH_FLOOR_SECONDS, left))


def durations(terminal: dict, accepted_at: float, observed_at: float) -> dict:
    """The job's own span, and its wait for the slot.

    `accepted_at` is when the POST returned, which for a queued job is when it started
    waiting. The studio's own timestamps say when the job actually began, so a figure
    taken beside another run does not quietly include a queue.
    """
    started_at = terminal.get("started_at")
    finished_at = terminal.get("finished_at")
    if not isinstance(started_at, (int, float)):
        return {"active": round(observed_at - accepted_at, 1)}
    end = finished_at if isinstance(finished_at, (int, float)) else observed_at
    return {
        "queue_wait": round(max(0.0, started_at - accepted_at), 1),
        "active": round(max(0.0, end - started_at), 1),
    }


def await_terminal(base: str, operation: str, deadline: float, accepted_at: float) -> dict | None:
    """Poll until the operation ends, then return its state. None means the deadline.

    A 404 is an answer, not a flaky link: a studio that restarted between two runs has
    forgotten the operation the checkpoint names, and waiting longer cannot bring it back.
    """
    stalls = 0
    asked = False
    while True:
        # Ask once before judging the deadline: a resumed operation can be older than the
        # deadline and long finished, and its answer is the record, not a timeout.
        if asked and deadline and time.time() - accepted_at > deadline:
            return None
        asked = True
        try:
            state = call(base, f"/api/v1/operations/{operation}", timeout=poll_timeout(deadline, accepted_at))
        except urllib.error.HTTPError as failure:
            if failure.code == 404:
                raise OperationGone(operation) from None
            stalls += 1
            print(f"  poll failed ({failure}); retry {stalls}", flush=True)
            if stalls >= 10:
                raise
            time.sleep(2.0)
            continue
        except (TimeoutError, urllib.error.URLError) as failure:
            stalls += 1
            print(f"  poll failed ({failure}); retry {stalls}", flush=True)
            if stalls >= 10:
                raise
            time.sleep(2.0)
            continue
        stalls = 0
        if state["status"] in ("succeeded", "failed", "cancelled"):
            return state
        time.sleep(POLL_SECONDS)


def request_cancel(base: str, operation: str) -> bool:
    with contextlib.suppress(Exception):
        call(base, f"/api/v1/operations/{operation}/cancel", {}, method="POST", timeout=30)
        return True
    return False


def _drive(
    base: str,
    case: dict,
    machine: str,
    payload: dict,
    fingerprint_value: str,
    phase_path: Path,
    out: Path,
    started: float,
    deadline: float,
    force: bool = False,
) -> dict:
    """Submit unless this campaign already has an operation, then wait for it to end.

    An operation that finished but whose result never arrived is fetched here rather than
    generated again, so a dropped download costs a download and not a GPU run. A studio
    that restarted has forgotten the operation, and then this submits the case again.
    """
    resumed = {} if force else read_checkpoint(phase_path, fingerprint_value)
    operation = resumed.get("operation")
    accepted_at = resumed.get("accepted_at")
    submitted_now = False
    terminal = None
    if operation is not None:
        try:
            terminal = await_terminal(base, operation, deadline, accepted_at or started)
        except OperationGone:
            operation, terminal = None, None

    if operation is None:
        try:
            accepted = call(base, "/api/v1/operations", {"kind": case["kind"], **payload}, method="POST")
        except urllib.error.HTTPError as failure:
            return {"status": "rejected", "error": failure.read().decode()[:300]}
        operation = accepted["id"]
        accepted_at = time.time()
        submitted_now = True
        write_checkpoint(
            phase_path,
            {
                "operation": operation,
                "accepted_at": accepted_at,
                "fingerprint": fingerprint_value,
                "phase": "submitted",
            },
        )
        terminal = await_terminal(base, operation, deadline, accepted_at)

    if terminal is None:
        cancelled = request_cancel(base, operation)
        return {
            "status": "timeout",
            "operation": operation,
            "error": f"no terminal status within {deadline:g} s; cancel requested={cancelled}",
        }

    terminal_at = time.time()
    record = {"status": terminal["status"], "kind": case["kind"], "operation": operation}
    record["error"] = (terminal.get("error") or "")[:300]
    if accepted_at:
        record.update(durations(terminal, accepted_at, terminal_at))
    if submitted_now and accepted_at is not None:
        record["submit_to_accept"] = round(accepted_at - started, 1)
    write_checkpoint(phase_path, {**record, "accepted_at": accepted_at, "fingerprint": fingerprint_value})

    if terminal["status"] == "succeeded":
        fetched_at = time.time()
        try:
            with urllib.request.urlopen(
                f"{base}/api/v1/operations/{operation}/result",
                timeout=fetch_timeout(deadline, accepted_at or started),
            ) as answer:
                body = answer.read()
        except (urllib.error.URLError, OSError, http.client.HTTPException) as failure:
            # The row keeps the operation, so the next run fetches this result instead of
            # generating it again. A lost download must not read as a lost result.
            record.update(status="fetch_failed", error=f"the result did not arrive: {failure}"[:300])
            write_checkpoint(phase_path, {**record, "accepted_at": accepted_at, "fingerprint": fingerprint_value})
            return record
        record["fetch"] = round(time.time() - fetched_at, 1)
        facts = output_facts(body, case["kind"])
        record.update(facts)
        results = out.parent / "results" / machine
        results.mkdir(parents=True, exist_ok=True)
        # Two parts of the name, for two different collisions. The case-id digest keeps two
        # ids that read alike after slugging apart, and the media digest keeps a repeat
        # trial with different bytes a second file, so the earlier row keeps its own.
        name = f"{slug(case['id'])}-{sha256(case['id'].encode())[:8]}-{facts['sha256'][:16]}.bin"
        (results / name).write_bytes(body)
        record["file"] = f"results/{machine}/{name}"
        write_checkpoint(
            phase_path,
            {**record, "accepted_at": accepted_at, "fingerprint": fingerprint_value, "phase": "downloaded"},
        )
    return record


def run_case(
    base: str,
    case: dict,
    machine: str,
    fingerprint_value: str,
    assets: Path,
    digests: dict[str, str],
    work: Path,
    out: Path,
    deadline: float,
    force: bool = False,
) -> dict:
    """One case, with the free memory sampled from the submit to the terminal status.

    The sampler is the point of the row: a figure taken only at the two ends of a job
    misses the peak of a job that allocates and frees inside itself.
    """
    payload = resolve(case["machines"][machine], assets, digests)
    sampler = MemorySampler()
    sampler.start()
    started = time.time()
    try:
        record = _drive(
            base,
            case,
            machine,
            payload,
            fingerprint_value,
            checkpoint_path(work, machine, case["id"], out),
            out,
            started,
            deadline,
            force,
        )
    except Exception as error:
        # One case's HTTP failure is one row, not the end of the campaign. The row says
        # what happened, and a failed row is not a finished one, so the next run retries
        # this case and skips the cases that did finish.
        record = {"status": "case_failed", "error": f"{type(error).__name__}: {error}"[:300]}
    finally:
        # A download that throws must not leave this sampler running until the process
        # ends, and must not hide the exception that stopped the case.
        memory = sampler.finish()
    record.update({"id": case["id"], "fingerprint": fingerprint_value, "seconds": round(time.time() - started, 1)})
    record.update(memory)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--machine", required=True, choices=("cuda", "mlx"), help="the key in the manifest")
    parser.add_argument("--base", default="http://127.0.0.1:8899")
    parser.add_argument("--work", default="/tmp/parity")
    parser.add_argument("--matrix", default="", help="defaults to <work>/matrix.jsonl")
    parser.add_argument("--assets", default="", help="defaults to <work>/assets")
    parser.add_argument("--out", default="", help="defaults to <work>/results-<machine>.jsonl")
    parser.add_argument("--only", default="", help="run the cases whose id contains this text")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--deadline", type=float, default=1800.0, help="seconds one case may take, 0 for no limit")
    parser.add_argument("--force", action="store_true", help="run a case this campaign already finished")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit nonzero when a case did not succeed or none of the selected cases were run",
    )
    parser.add_argument("--list-cases", action="store_true", help="print the selected case ids and exit")
    parser.add_argument(
        "--reuse-compatible",
        action="store_true",
        help="reuse the campaign.json on disk even when this tree differs from it",
    )
    arguments = parser.parse_args()
    if not math.isfinite(arguments.deadline) or arguments.deadline < 0:
        raise SystemExit("--deadline must be zero or more seconds")

    work = Path(arguments.work)
    out = Path(arguments.out or work / f"results-{arguments.machine}.jsonl")
    assets = Path(arguments.assets or work / "assets")
    matrix = Path(arguments.matrix or work / "matrix.jsonl")
    cases = [json.loads(line) for line in matrix.read_text().splitlines()]
    if arguments.only:
        cases = [case for case in cases if arguments.only in case["id"]]
    if arguments.limit:
        cases = cases[: arguments.limit]
    if arguments.list_cases:
        for case in cases:
            print(case["id"])
        return 0

    digests = load_assets(work)
    manifest_path = work / f"campaign-{arguments.machine}.json"
    try:
        live = live_configuration(
            call(arguments.base, "/api/v1/state"),
            lambda workspace, backend_id: call(
                arguments.base,
                f"/api/v1/{WORKSPACE_ROUTES[workspace]}/backends/{backend_id}",
            ),
        )
    except (urllib.error.URLError, OSError) as failure:
        raise SystemExit(f"No studio at {arguments.base}: {failure}. Start one first.") from None
    recorded_build = (live["studio"].get("build") or {}).get("commit")
    runner_commit = git_sha()
    if recorded_build and "unknown" not in (recorded_build, runner_commit) and recorded_build != runner_commit:
        raise SystemExit(
            f"The studio at {arguments.base} runs {recorded_build}, and this runner is at {runner_commit}. "
            "A figure from one would be attributed to the other. Restart the studio from this checkout."
        )
    manifest = campaign_manifest(arguments.machine, digests, live)
    if manifest_path.is_file():
        recorded = json.loads(manifest_path.read_text())
        differing = sorted(key for key, value in manifest.items() if recorded.get(key) != value)
        if differing:
            # A flag that waived every difference attached new runs to a model the old
            # campaign never measured. Only what cannot change a figure may differ.
            harmless = set(differing) <= REUSABLE_FIELDS
            if not (arguments.reuse_compatible and harmless):
                note = (
                    " --reuse-compatible covers only "
                    + ", ".join(sorted(REUSABLE_FIELDS))
                    + ", and this is not one of those."
                    if arguments.reuse_compatible
                    else " Start a new --work directory, or pass --reuse-compatible to keep the old results."
                )
                raise SystemExit(f"{manifest_path.name} records a different {', '.join(differing)}.{note}")
        manifest = recorded
    else:
        manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")

    fingerprints = {case["id"]: fingerprint(case, manifest) for case in cases}
    repair_tail(out)
    finished = set() if arguments.force else done(out, fingerprints, work)
    print(f"{arguments.machine}: {len(cases)} cases, {len(finished)} already done", flush=True)

    ran = skipped = failed = 0
    for case in cases:
        if case["id"] in finished:
            skipped += 1
            continue
        record = run_case(
            arguments.base,
            case,
            arguments.machine,
            fingerprints[case["id"]],
            assets,
            digests,
            work,
            out,
            arguments.deadline,
            arguments.force,
        )
        print(f"{case['id']}: {record['status']} {record['seconds']} s {record.get('error', '')}", flush=True)
        with out.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        ran += 1
        failed += record["status"] != "succeeded"
    print(f"{arguments.machine}: ran {ran}, skipped {skipped}, did not succeed {failed}", flush=True)
    if not arguments.strict:
        return 0
    complete = done(out, fingerprints, work)
    return 0 if all(case["id"] in complete for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
