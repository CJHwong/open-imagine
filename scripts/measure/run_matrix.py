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
import json
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


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def media_bytes(body: bytes, kind: str) -> bytes:
    """The artifact itself. An image crosses as JSON with the PNG inside it; every other
    kind crosses as the file."""
    if kind != "image" or body[:1] != b"{":
        return body
    return base64.b64decode(json.loads(body)["images"][0]["png_base64"])


def output_facts(body: bytes, kind: str) -> dict:
    """What the bytes say about themselves.

    A status of succeeded proves that the API answered, and nothing about the answer. A
    video that lost its audio track still succeeds. These facts are cheap, they need no
    dependency, and they make the two machines comparable before the times are.
    """
    media = media_bytes(body, kind)
    facts = {"sha256": sha256(media), "bytes": len(media)}
    if kind == "image" and media[:8] == b"\x89PNG\r\n\x1a\n":
        facts.update(width=int.from_bytes(media[16:20], "big"), height=int.from_bytes(media[20:24], "big"))
    elif kind in ("voice", "music") and media[:4] == b"RIFF":
        rate = int.from_bytes(media[24:28], "little")
        channels = int.from_bytes(media[22:24], "little")
        widths = int.from_bytes(media[34:36], "little")
        marker = media.find(b"data")
        frames = int.from_bytes(media[marker + 4 : marker + 8], "little") if marker >= 0 else 0
        stride = rate * channels * widths // 8
        facts.update(sample_rate=rate, channels=channels, seconds=round(frames / stride, 2) if stride else 0)
    elif kind == "video":
        # The handler atom names its track. A missing one means the encode dropped the audio.
        facts["audio_track"] = b"soun" in media
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


def call(base: str, path: str, body: dict | None = None, method: str = "GET", timeout: int = 120):
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


def campaign_manifest(machine: str, digests: dict[str, str]) -> dict:
    """Everything a result depends on that is not the payload itself."""
    return {
        "machine": machine,
        "git": git_sha(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "assets": digests,
    }


def fingerprint(case: dict, manifest: dict) -> str:
    return sha256(json.dumps({"manifest": manifest, "case": case}, sort_keys=True).encode())[:16]


def records(path: Path) -> dict[str, dict]:
    """Every record in the file, with the last line for a case winning."""
    if not path.is_file():
        return {}
    picked = {}
    for line in path.read_text().splitlines():
        record = json.loads(line)
        picked[record["id"]] = record
    return picked


def done(path: Path, fingerprints: dict[str, str]) -> set[str]:
    """The cases this campaign already finished, and only those."""
    return {
        case_id
        for case_id, record in records(path).items()
        if record.get("status") == "succeeded" and record.get("fingerprint") == fingerprints.get(case_id)
    }


def checkpoint_path(work: Path, machine: str, case_id: str) -> Path:
    directory = work / f"phases-{machine}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (slug(case_id) + ".json")


def read_checkpoint(path: Path, expected: str) -> dict:
    if not path.is_file():
        return {}
    record = json.loads(path.read_text())
    return record if record.get("fingerprint") == expected else {}


def write_checkpoint(path: Path, record: dict) -> None:
    """Write whole, then move into place, so a crash leaves no half file."""
    scratch = path.with_suffix(".tmp")
    scratch.write_text(json.dumps(record))
    scratch.replace(path)


class OperationGone(Exception):
    """The studio no longer holds this operation, so its record cannot be trusted."""


def await_terminal(base: str, operation: str, deadline: float, accepted_at: float) -> dict | None:
    """Poll until the operation ends, then return its state. None means the deadline.

    A 404 is an answer, not a flaky link: a studio that restarted between two runs has
    forgotten the operation the checkpoint names, and waiting longer cannot bring it back.
    """
    stalls = 0
    while True:
        if deadline and time.time() - accepted_at > deadline:
            return None
        try:
            state = call(base, f"/api/v1/operations/{operation}", timeout=180)
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
    record = {"status": terminal["status"], "operation": operation, "error": (terminal.get("error") or "")[:300]}
    if accepted_at:
        record["active"] = round(terminal_at - accepted_at, 1)
    if submitted_now and accepted_at is not None:
        record["submit_to_accept"] = round(accepted_at - started, 1)
    write_checkpoint(phase_path, {**record, "accepted_at": accepted_at, "fingerprint": fingerprint_value})

    if terminal["status"] == "succeeded":
        fetched_at = time.time()
        with urllib.request.urlopen(f"{base}/api/v1/operations/{operation}/result", timeout=600) as answer:
            body = answer.read()
        record["fetch"] = round(time.time() - fetched_at, 1)
        record.update(output_facts(body, case["kind"]))
        results = out.parent / "results" / machine
        results.mkdir(parents=True, exist_ok=True)
        name = f"{slug(case['id'])}-{fingerprint_value[:8]}.bin"
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
    record = _drive(
        base,
        case,
        machine,
        payload,
        fingerprint_value,
        checkpoint_path(work, machine, case["id"]),
        out,
        started,
        deadline,
        force,
    )
    record.update({"id": case["id"], "fingerprint": fingerprint_value, "seconds": round(time.time() - started, 1)})
    record.update(sampler.finish())
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
    parser.add_argument("--list-cases", action="store_true", help="print the selected case ids and exit")
    parser.add_argument(
        "--reuse-compatible",
        action="store_true",
        help="reuse the campaign.json on disk even when this tree differs from it",
    )
    arguments = parser.parse_args()

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
    manifest = campaign_manifest(arguments.machine, digests)
    if manifest_path.is_file():
        recorded = json.loads(manifest_path.read_text())
        differing = sorted(key for key, value in manifest.items() if recorded.get(key) != value)
        if differing and not arguments.reuse_compatible:
            raise SystemExit(
                f"{manifest_path.name} records a different {', '.join(differing)}. "
                "Start a new --work directory, or pass --reuse-compatible to keep the old results."
            )
        manifest = recorded
    else:
        manifest_path.write_text(json.dumps(manifest, indent=1) + "\n")

    fingerprints = {case["id"]: fingerprint(case, manifest) for case in cases}
    finished = set() if arguments.force else done(out, fingerprints)
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
        ran += 1
        failed += record["status"] != "succeeded"
    print(f"{arguments.machine}: ran {ran}, skipped {skipped}, did not succeed {failed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
