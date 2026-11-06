#!/usr/bin/env python3
"""Owned Studio slots, immutable attempts, per-job video approval, explicit exports.

Queue paths resolve from project.json, never the current directory. Each job has
name, request, out, allowance_seconds, and optional references [{path, ...API fields}].
Video jobs additionally name shot and must match staging.submission_spec exactly.
No submission is retried automatically, including a timed-out POST.
"""

import argparse
import base64
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from contextlib import suppress
from pathlib import Path

REVIEW = Path(__file__).with_name("review.py")


def resolve_repo(value=None):
    """Find the Studio checkout: --repo, then STUDIO_REPO, then the current directory."""
    candidates = [(value, "--repo"), (os.environ.get("STUDIO_REPO"), "STUDIO_REPO")]
    for candidate, source in candidates:
        if candidate is None:
            continue
        path = Path(candidate).expanduser().resolve()
        if (path / "studio.toml").is_file():
            return path
        raise SystemExit(f"{source} does not name a Studio checkout: {path}")
    current = Path.cwd().resolve()
    if (current / "studio.toml").is_file():
        return current
    raise SystemExit("No Studio checkout found: pass --repo PATH or set STUDIO_REPO")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, obj):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2)


def local(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or ".env" in path.name:
        raise ValueError(f"Not a project-local media path: {value}")
    return path


def require_generation_permission(project, kind=None):
    """Honor a producer's CPU-only instruction before touching a slot or server."""
    data = json.loads(project.read_text())
    if data.get("execution_constraints", {}).get("gpu_allowed") is False:
        raise RuntimeError("GPU use is disabled by the producer; CPU preparation only")
    hold = data.get("generation_hold") or {}
    if hold.get("active", True) and hold and (kind is None or kind in hold.get("scope", [])):
        raise RuntimeError("Generation is on hold: " + hold.get("resume_requires", "producer direction required"))


class Token:
    def __init__(self, path, session, minutes):
        self.path = path
        self.text = f"{session} {os.getpid()} {time.time():.3f} {time.time() + minutes * 60:.3f} {uuid.uuid4()}\n"

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x") as stream:
            stream.write(self.text)

    def release(self):
        if not self.path.exists() or self.path.read_text() != self.text:
            raise RuntimeError("GPU token ownership changed; token left alone")
        subprocess.run(["rm", str(self.path)], check=True)


def busy_processes():
    listing = subprocess.check_output(["ps", "-axo", "pid,command"], text=True)
    found = []
    for line in listing.splitlines()[1:]:
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        command = parts[1]
        # The repo's explicit --stub mode fakes every model and uses no GPU.
        if "--stub" in command.split():
            continue
        executable = Path(command.split()[0]).name
        if executable.startswith(("python", "studio", "uv", "ltx")) and any(
            item in command for item in ("/bin/studio", "studio --", "ltx_pipelines", "ltx-2-mlx", "drama3_child")
        ):
            found.append(line.strip())
    return found


def port_free(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Port {port} occupied; existing server left alone") from exc


class Slot:
    def __init__(self, root, session, minutes=30, port=8817, repo=None):
        if not 0 < minutes <= 30:
            raise ValueError("A normal slot must be at most 30 minutes")
        self.root, self.port, self.minutes = root, port, minutes
        self.repo = repo
        self.base = f"http://127.0.0.1:{port}"
        self.token = Token(Path.home() / "tmp/gpu.token", session, minutes)
        self.server = None

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    def assert_owned(self):
        if self.server is None or self.server.poll() is not None or self.token.path.read_text() != self.token.text:
            raise RuntimeError("Own live server and GPU token are required before submission")

    def __enter__(self):
        self.repo = resolve_repo(self.repo)
        # Check the user's port and all model processes before taking a slot.
        port_free(8765)
        port_free(self.port)
        if found := busy_processes():
            raise RuntimeError("GPU processes active: " + "; ".join(found))
        self.token.acquire()
        self.deadline = time.monotonic() + self.minutes * 60
        try:
            port_free(8765)
            port_free(self.port)
            if busy_processes():
                raise RuntimeError("A model process appeared; no server started")
            log_path = self.root / "operations" / f"server-{uuid.uuid4().hex}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("x") as log:
                self.server = subprocess.Popen(
                    ["uv", "run", "studio", "--port", str(self.port), "--backend", "qwen21_turbo"],
                    cwd=self.repo,
                    env={**os.environ, "PATH": "/opt/homebrew/bin:" + os.environ.get("PATH", "")},
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            for _ in range(90):
                if self.server.poll() is not None:
                    raise RuntimeError(f"Own server exited; inspect {log_path}")
                try:
                    self.call("GET", "/api/v1/state")
                    # Reject a foreign listener even if it won a bind race.
                    listeners = subprocess.check_output(["lsof", "-t", f"-iTCP:{self.port}", "-sTCP:LISTEN"], text=True)
                    groups = {
                        int(subprocess.check_output(["ps", "-o", "pgid=", "-p", pid], text=True))
                        for pid in listeners.split()
                    }
                    if groups != {self.server.pid}:
                        raise RuntimeError("Listener does not belong to own server process group")
                    print(f"GPU slot owned, server port {self.port}, PID {self.server.pid}", flush=True)
                    return self
                except (OSError, ConnectionError):
                    time.sleep(2)
            raise RuntimeError(f"Own server failed to start; inspect {log_path}")
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *exc):
        if self.server is not None:
            # This group was created by this runner; never match processes by name.
            with suppress(ProcessLookupError):
                os.killpg(self.server.pid, signal.SIGTERM)
            self.server.wait(timeout=30)
            group = subprocess.check_output(["ps", "-axo", "pgid="], text=True)
            if str(self.server.pid) in group.split():
                raise RuntimeError("Own child still running; token retained for investigation")
        self.token.release()
        print("GPU free", flush=True)


def job_spec(job):
    return {key: job.get(key) for key in ("request", "references")}


def gate_job(project, job):
    if job["request"]["kind"] != "video":
        return
    before = project.read_bytes()
    data = json.loads(before)
    shot = next((s for s in data["shots"] if s["id"] == job.get("shot")), None)
    staging = shot.get("staging", {}) if shot else {}
    specs = staging.get("submission_specs", [staging.get("submission_spec")])
    if job_spec(job) not in specs:
        raise ValueError("Actual video job differs from the reviewed submission specification")
    for media, expected in staging.get("review_media_sha256", {}).items():
        if digest(local(project.parent, media).read_bytes()) != expected:
            raise ValueError("Reviewed guide changed; renew its review and approval before video")
    result = subprocess.run(
        [sys.executable, str(REVIEW), "gate", str(project), "--shots", job["shot"]], capture_output=True, text=True
    )
    if result.returncode:
        raise RuntimeError("Video gate closed: " + result.stdout + result.stderr)
    if project.read_bytes() != before:
        raise RuntimeError("Project changed while checking approval")


def validate_media(path, kind):
    if kind == "image":
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
    else:
        info = json.loads(
            subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], text=True
            )
        )
        needed = "video" if kind == "video" else "audio"
        if not any(s["codec_type"] == needed for s in info["streams"]) or float(info["format"]["duration"]) <= 0:
            raise ValueError("Downloaded media has no expected stream/duration")


def run_job(slot, project, job):
    project = project.resolve()
    require_generation_permission(project, job["request"]["kind"])
    root = project.parent
    if job["request"].get("count", 1) != 1 or "items" in job["request"]:
        raise ValueError("Each immutable attempt must submit exactly one result")
    if any(field in job["request"] for field in ("references", "reference", "audio", "clip")):
        raise ValueError("Inline media is not allowed; use saved local reference paths")
    out = local(root, job["out"])
    record = out.with_suffix(out.suffix + ".run")
    spec = job_spec(job)
    references = []
    for ref in job.get("references", []):
        data = local(root, ref["path"]).read_bytes()
        references.append((ref, data))
    signature = digest(
        json.dumps({"spec": spec, "inputs": [digest(b) for _, b in references]}, sort_keys=True).encode()
    )
    marker = record / "complete.json"
    if marker.exists():
        completed = json.loads(marker.read_text())
        if completed["signature"] != signature or not out.exists() or completed["sha256"] != digest(out.read_bytes()):
            raise ValueError("Saved output or request changed; preserve it and create a new attempt")
        validate_media(out, job["request"]["kind"])
        print(f"Verified existing attempt: {job['name']}", flush=True)
        return
    if out.exists() or record.exists():
        raise FileExistsError("Incomplete attempt preserved; recover its operation instead of resubmitting")
    if time.monotonic() + job["allowance_seconds"] > slot.deadline:
        raise RuntimeError("Job does not fit this GPU slot; nothing submitted")
    record.mkdir(parents=True)
    save(record / "request.json", {"job": job, "signature": signature})
    body = dict(job["request"])
    body["client_id"] = f"{json.loads(project.read_text())['id']}-{uuid.uuid4()}"
    save(record / "client.json", {"client_id": body["client_id"]})
    if references:
        body["references"] = []
        for index, (ref, data) in enumerate(references):
            (record / f"reference-{index:02}.png").write_bytes(data)
            fields = {k: v for k, v in ref.items() if k != "path"}
            fields["image" if body["kind"] == "video" else "png_base64"] = base64.b64encode(data).decode()
            body["references"].append(fields)
    # Transport bytes come from saved input snapshots. Recheck the live bytes and
    # gate after all preparation, directly before the only POST boundary.
    for ref, data in references:
        if local(root, ref["path"]).read_bytes() != data:
            raise RuntimeError("Input changed during preparation")
    if body["kind"] == "video":
        limits = json.loads(project.read_text())["settings"]
        prior = [json.loads(p.read_text()) for p in root.rglob("submitted.json")]
        prior = [p for p in prior if p.get("kind") == "video"]
        if (
            len(prior) >= limits["video_attempt_limit"]
            or sum(p["shot"] == job["shot"] for p in prior) >= limits["video_attempts_per_shot"]
        ):
            raise RuntimeError("Video attempt budget exhausted; no submission")
    slot.assert_owned()
    gate_job(project, job)
    started = time.monotonic()
    save(
        record / "submitted.json",
        {"kind": body["kind"], "shot": job.get("shot"), "at": time.time(), "client_id": body["client_id"]},
    )
    accepted = json.loads(slot.call("POST", "/api/v1/operations", body))
    save(record / "accepted.json", accepted)
    operation_id = accepted["id"]
    while True:
        status = json.loads(slot.call("GET", f"/api/v1/operations/{operation_id}"))
        if status["status"] in ("succeeded", "failed", "cancelled"):
            break
        if time.monotonic() > slot.deadline:
            slot.call("POST", f"/api/v1/operations/{operation_id}/cancel", {})
            raise RuntimeError("Own operation cancelled at slot deadline; attempt preserved")
        time.sleep(3)
    save(record / "terminal.json", status)
    if status["status"] != "succeeded":
        raise RuntimeError(f"Operation ended: {status}")
    payload = slot.call("GET", status.get("result_url") or f"/api/v1/operations/{operation_id}/result")
    kind = body["kind"]
    if kind == "image":
        result = json.loads(payload)
        image = result["images"][0]
        payload = base64.b64decode(image.pop("png_base64"))
        save(record / "result.json", result)
    with out.open("xb") as stream:
        stream.write(payload)
    validate_media(out, kind)
    save(
        marker,
        {
            "signature": signature,
            "sha256": digest(payload),
            "operation_id": operation_id,
            "elapsed": round(time.monotonic() - started, 2),
        },
    )
    print(f"Completed {job['name']} -> {out.relative_to(root)}", flush=True)


def register_export(project, path, label, kind):
    project = project.resolve()
    root = project.parent
    media = local(root, path)
    validate_media(media, "video")
    data = json.loads(project.read_text())
    item = {"path": str(media.relative_to(root)), "label": label, "kind": kind, "sha256": digest(media.read_bytes())}
    data["exports"] = [item] + [x for x in data.get("exports", []) if x["path"] != item["path"]]
    data["revision"] += 1
    data.setdefault("history", []).append({"kind": "export_registered", **item})
    import review

    review.write_atomic(project, data)
    subprocess.run([sys.executable, str(REVIEW), "build", str(project)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    jobs = sub.add_parser("run")
    jobs.add_argument("queue", type=Path)
    jobs.add_argument("--minutes", type=int, default=30)
    jobs.add_argument("--port", type=int, default=8817)
    jobs.add_argument("--repo", help="Studio checkout; defaults to STUDIO_REPO or the current directory")
    discover = sub.add_parser("discover")
    discover.add_argument("--port", type=int, default=8817)
    discover.add_argument("--repo", help="Studio checkout; defaults to STUDIO_REPO or the current directory")
    export = sub.add_parser("export")
    export.add_argument("path")
    export.add_argument("--label", required=True)
    export.add_argument("--kind", choices=("animatic", "film"), required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    if args.command == "export":
        register_export(project, args.path, args.label, args.kind)
        return
    require_generation_permission(project)
    with Slot(
        project.parent,
        f"film-{json.loads(project.read_text())['id']}",
        getattr(args, "minutes", 5),
        args.port,
        resolve_repo(args.repo),
    ) as slot:
        if args.command == "discover":
            folder = project.parent / "operations" / f"discovery-{uuid.uuid4().hex}"
            folder.mkdir()
            for name, route in (
                ("studio", "/api/v1/studio"),
                ("state", "/api/v1/state"),
                ("openapi", "/api/v1/openapi.json"),
                ("image", "/api/v1/images/backends/qwen21_turbo"),
                ("voice", "/api/v1/voice/backends/drama3"),
                ("video", "/api/v1/videos/backends/ltx25_mlx"),
            ):
                save(folder / f"{name}.json", json.loads(slot.call("GET", route)))
            print(f"Discovery saved: {folder}")
        else:
            queue = json.loads(local(project.parent, str(args.queue)).read_text())
            for job in queue:
                run_job(slot, project, job)


if __name__ == "__main__":
    main()
