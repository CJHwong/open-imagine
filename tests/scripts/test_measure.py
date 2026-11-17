"""CPU-only checks for the parity harness: a fake studio answers, the runner records.

The harness is what a performance conclusion rests on, so its own claims get tests: the
peak it prints, the campaign it reuses, the deadline it enforces, and the report that has
to say when two figures came from different campaigns.
"""

import importlib.util
import json
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

MEASURE = Path(__file__).parents[2] / "scripts" / "measure"


def load(name):
    spec = importlib.util.spec_from_file_location(name, MEASURE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_matrix = load("run_matrix")
report = load("report")
build_assets = load("build_assets")


class Studio:
    """A studio that answers the routes the runner uses, and does nothing real."""

    def __init__(self, running_seconds=0.0, final="succeeded"):
        self.running_seconds = running_seconds
        self.final = final
        self.accepted_at = None
        self.submissions = 0
        self.cancels = 0
        self.result_reads = 0
        self.payloads = []
        self.base = ""
        self.known = True

    def forget(self):
        """What a restart does: the operation it accepted is no longer anywhere."""
        self.known = False

    def status(self):
        if self.accepted_at is not None and time.time() - self.accepted_at < self.running_seconds:
            return "running"
        return self.final

    @property
    def running(self):
        return self.status() == "running"


def handler_for(studio):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            """Nothing here belongs on the terminal."""

        def _send(self, document, status=200):
            body = b"" if document is None else json.dumps(document).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            document = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/v1/operations":
                studio.submissions += 1
                studio.accepted_at = time.time()
                studio.payloads.append(document)
                studio.known = True
                self._send({"id": "op-1"}, 201)
            elif self.path.endswith("/cancel"):
                studio.cancels += 1
                self._send(None, 204)
            else:
                self._send({"error": "no route"}, 404)

        def do_GET(self):
            if not studio.known:
                self._send({"error": "The operation expired or does not exist."}, 404)
            elif self.path == "/api/v1/operations/op-1":
                self._send({"status": studio.status(), "error": None})
            elif self.path == "/api/v1/operations/op-1/result":
                studio.result_reads += 1
                self.send_response(200)
                self.send_header("Content-Length", "5")
                self.end_headers()
                self.wfile.write(b"bytes")
            else:
                self._send({"error": "no route"}, 404)

    return Handler


@contextmanager
def served(**options):
    studio = Studio(**options)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(studio))
    studio.base = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield studio
    finally:
        server.shutdown()
        server.server_close()


def one_case(case_id="case/one", kind="image"):
    return {"id": case_id, "kind": kind, "machines": {"mlx": {"prompt": "pear"}, "cuda": {"prompt": "pear"}}}


@pytest.fixture
def work(tmp_path):
    (tmp_path / "assets").mkdir()
    return tmp_path


def run(studio, work, case, monkeypatch, deadline=5.0, machine="mlx", force=False):
    monkeypatch.setattr(run_matrix, "POLL_SECONDS", 0.01)
    return run_matrix.run_case(
        studio.base,
        case,
        machine,
        run_matrix.fingerprint(case, {"machine": machine}),
        work / "assets",
        {},
        work,
        work / f"results-{machine}.jsonl",
        deadline,
        force,
    )


def test_the_peak_memory_sample_sees_a_drop_that_ends_before_the_result(work, monkeypatch):
    """The figure is the lowest sample during the run, not the difference between the two
    ends of it. A job that allocates and frees inside itself shows nothing at its ends."""
    monkeypatch.setattr(run_matrix, "memory_free_gib", lambda: 40.0 if studio.running else 100.0)
    with served(running_seconds=0.5) as studio:
        record = run(studio, work, one_case(), monkeypatch)

    assert record["status"] == "succeeded"
    assert record["free_start_gib"] == 100.0
    assert record["free_min_gib"] == 40.0
    assert record["peak_drop_gib"] == 60.0
    assert record["free_end_gib"] == 100.0


def test_a_finished_operation_is_fetched_again_without_being_generated_again(work, monkeypatch):
    """A download that failed after a successful run costs a download, not another run."""
    with served() as studio:
        first = run(studio, work, one_case(), monkeypatch)
        assert first["status"] == "succeeded" and studio.submissions == 1

        again = run(studio, work, one_case(), monkeypatch)

    assert again["status"] == "succeeded"
    assert studio.submissions == 1
    assert studio.result_reads == 2


def test_a_checkpoint_the_studio_forgot_is_submitted_again(work, monkeypatch):
    """A restart drops the in-memory operation. Polling it cannot end, and the case must
    run again rather than be lost to a 404."""
    with served() as studio:
        assert run(studio, work, one_case(), monkeypatch)["status"] == "succeeded"
        studio.forget()

        again = run(studio, work, one_case(), monkeypatch)

    assert again["status"] == "succeeded"
    assert studio.submissions == 2


def test_force_runs_the_case_again_instead_of_reusing_its_operation(work, monkeypatch):
    """A forced repeat is a new request. Reusing the checkpoint would report the old one
    as if it were this run's, which reads as zero seconds."""
    with served() as studio:
        assert run(studio, work, one_case(), monkeypatch)["status"] == "succeeded"

        again = run(studio, work, one_case(), monkeypatch, force=True)

    assert again["status"] == "succeeded"
    assert studio.submissions == 2


def test_a_case_that_never_ends_is_recorded_as_a_timeout_and_cancelled(work, monkeypatch):
    with served(running_seconds=600.0) as studio:
        record = run(studio, work, one_case(), monkeypatch, deadline=0.2)

    assert record["status"] == "timeout"
    assert "cancel requested=True" in record["error"]
    assert studio.cancels == 1


def test_two_ids_that_read_alike_write_different_files(work, monkeypatch):
    with served() as studio:
        first = run(studio, work, one_case("a/b"), monkeypatch)
        second = run(studio, work, one_case("a_b"), monkeypatch)

    assert first["file"] != second["file"]
    assert (work / first["file"]).is_file() and (work / second["file"]).is_file()


def test_a_result_from_another_commit_is_not_reused(work, monkeypatch):
    """A model change is not a new case, it is a new campaign. The old figure stays put."""
    case = one_case()
    before = run_matrix.campaign_manifest("mlx", {})
    after = {**before, "git": "0000000"}
    assert run_matrix.fingerprint(case, before) != run_matrix.fingerprint(case, after)

    out = work / "results-mlx.jsonl"
    out.write_text(
        json.dumps({"id": case["id"], "status": "succeeded", "fingerprint": run_matrix.fingerprint(case, before)})
        + "\n"
    )

    assert run_matrix.done(out, {case["id"]: run_matrix.fingerprint(case, before)}) == {case["id"]}
    assert run_matrix.done(out, {case["id"]: run_matrix.fingerprint(case, after)}) == set()


def test_an_asset_that_no_longer_matches_its_digest_is_refused(work):
    (work / "assets" / "ref.png").write_bytes(b"changed")
    (work / "assets.sha256").write_text("0  ref.png\n")

    with pytest.raises(SystemExit, match="same bytes"):
        run_matrix.resolve({"$file": "ref.png"}, work / "assets", run_matrix.load_assets(work))


def test_a_case_that_cites_an_unlisted_asset_is_refused(work):
    (work / "assets" / "ref.png").write_bytes(b"bytes")

    assert run_matrix.load_assets(work) == {}
    with pytest.raises(SystemExit, match="no digest"):
        run_matrix.resolve({"$file": "ref.png"}, work / "assets", run_matrix.load_assets(work))


def test_a_result_is_checked_against_what_its_own_bytes_say():
    """A succeeded status says the API answered. These facts say what it answered with."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (640).to_bytes(4, "big") + (480).to_bytes(4, "big")
    wrapped = json.dumps({"images": [{"png_base64": __import__("base64").b64encode(png).decode()}]}).encode()

    facts = run_matrix.output_facts(wrapped, "image")
    assert (facts["width"], facts["height"]) == (640, 480)
    assert facts["bytes"] == len(png)

    wav = (
        b"RIFF" + (0).to_bytes(4, "little") + b"WAVE"
        b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (2).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (64000).to_bytes(4, "little")
        + (4).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (64000).to_bytes(4, "little")
    )
    spoken = run_matrix.output_facts(wav, "voice")
    assert (spoken["sample_rate"], spoken["channels"], spoken["seconds"]) == (16000, 2, 1.0)

    assert run_matrix.output_facts(b"...ftyp...soun...", "video")["audio_track"] is True
    assert run_matrix.output_facts(b"...ftyp...vide...", "video")["audio_track"] is False


def test_building_assets_again_over_an_owned_directory_is_refused(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets.sha256").write_text("0  ref.png\n")
    monkeypatch.setattr(
        sys, "argv", ["build_assets.py", "--work", str(tmp_path), "--image-backend", "a", "--voice-backend", "b"]
    )

    with pytest.raises(SystemExit, match="copying the directory"):
        build_assets.main()


def test_the_report_does_not_compare_figures_from_two_campaigns():
    record = {"status": "succeeded", "seconds": 12.0, "active": 9.0, "fingerprint": "old"}

    assert report.cell(record, "new") == "other campaign"
    assert report.cell(record, "old") == "9.0"
    assert report.cell({"status": "failed", "seconds": 3.0}, "old") == "failed"
    assert report.cell(None, "old") == "not run"


def test_the_report_says_when_the_machines_differ():
    lines = report.provenance(
        Path("/nowhere"), {"mlx": {"git": "aaa", "assets": {}}, "cuda": {"git": "bbb", "assets": {}}}
    )

    assert any("differ in git" in line for line in lines)
    assert any("no campaign manifest" in line for line in report.provenance(Path("/nowhere"), {"mlx": {}, "cuda": {}}))
