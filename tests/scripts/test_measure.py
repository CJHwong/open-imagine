"""CPU-only checks for the parity harness: a fake studio answers, the runner records.

The harness is what a performance conclusion rests on, so its own claims get tests: the
peak it prints, the campaign it reuses, the deadline it enforces, and the report that has
to say when two figures came from different campaigns.
"""

import base64
import importlib.util
import json
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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
        self.result_failures = 0
        self.bodies = []
        self.build = {}

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
                if studio.result_failures:
                    studio.result_failures -= 1
                    self._send({"error": "the result is not ready"}, 500)
                    return
                body = studio.bodies.pop(0) if studio.bodies else b"bytes"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/v1/state":
                self._send({"studio": {"build": studio.build}})
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

    with served() as studio:
        row = run(studio, work, case, monkeypatch)
    out = work / "results-mlx.jsonl"
    out.write_text(json.dumps({**row, "fingerprint": run_matrix.fingerprint(case, before)}) + "\n")

    assert run_matrix.done(out, {case["id"]: run_matrix.fingerprint(case, before)}, work) == {case["id"]}
    assert run_matrix.done(out, {case["id"]: run_matrix.fingerprint(case, after)}, work) == set()


def test_a_success_whose_artifact_is_gone_is_not_reused(work, monkeypatch):
    """A results file copied between machines can travel without its media, and a run
    that trusted the row would report a campaign nobody can look at."""
    case = one_case()
    with served() as studio:
        row = run(studio, work, case, monkeypatch)
    out = work / "results-mlx.jsonl"
    out.write_text(json.dumps(row) + "\n")
    fingerprints = {case["id"]: row["fingerprint"]}
    assert run_matrix.done(out, fingerprints, work) == {case["id"]}

    (work / row["file"]).unlink()

    assert run_matrix.done(out, fingerprints, work) == set()


def test_a_success_whose_artifact_changed_is_not_reused(work, monkeypatch):
    case = one_case()
    with served() as studio:
        row = run(studio, work, case, monkeypatch)
    out = work / "results-mlx.jsonl"
    out.write_text(json.dumps(row) + "\n")
    (work / row["file"]).write_bytes(b"trunc")

    assert run_matrix.done(out, {case["id"]: row["fingerprint"]}, work) == set()


def test_a_saved_image_is_checked_through_its_json_wrapper(work):
    """The row hashes the decoded picture. The file holds the JSON that carried it."""
    picture = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (32).to_bytes(4, "big") + (32).to_bytes(4, "big")
    wrapped = json.dumps({"images": [{"png_base64": base64.b64encode(picture).decode()}]}).encode()
    (work / "results").mkdir()
    (work / "results" / "one.bin").write_bytes(wrapped)
    record = {"file": "results/one.bin", "sha256": run_matrix.sha256(picture), "kind": "image"}

    assert run_matrix.saved(work, record)

    record["sha256"] = "0" * 64
    assert not run_matrix.saved(work, record)


def test_a_failed_download_is_recorded_and_the_next_run_fetches_it(work, monkeypatch):
    """A lost download is not a lost result. The row keeps the operation, so the next run
    collects the bytes instead of spending the GPU again."""
    with served() as studio:
        studio.result_failures = 1
        first = run(studio, work, one_case(), monkeypatch)

        assert first["status"] == "fetch_failed"
        assert "did not arrive" in first["error"]
        assert studio.submissions == 1

        again = run(studio, work, one_case(), monkeypatch)

    assert again["status"] == "succeeded"
    assert studio.submissions == 1
    assert studio.result_reads == 2


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


def box(kind: bytes, body: bytes) -> bytes:
    return (len(body) + 8).to_bytes(4, "big") + kind + body


def chunk(kind: bytes, body: bytes) -> bytes:
    """A RIFF chunk: a little-endian size, and a pad byte after an odd body."""
    return kind + len(body).to_bytes(4, "little") + body + (b"\x00" if len(body) % 2 else b"")


def handler_box(handler: bytes) -> bytes:
    # hdlr: version and flags, a pre-defined field, then the handler name.
    return box(b"hdlr", b"\x00" * 8 + handler + b"\x00" * 12)


def test_a_result_is_checked_against_what_its_own_bytes_say():
    """A succeeded status says the API answered. These facts say what it answered with."""
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + (640).to_bytes(4, "big")
        + (480).to_bytes(4, "big")
        + b"\x00\x00\x00\x00IEND\x00\x00\x00\x00"
    )
    wrapped = json.dumps({"images": [{"png_base64": base64.b64encode(png).decode()}]}).encode()

    facts = run_matrix.output_facts(wrapped, "image")
    assert (facts["width"], facts["height"]) == (640, 480)
    assert facts["bytes"] == len(png)

    frames = b"\x00" * 64000
    wav = (
        b"RIFF"
        + (36 + len(frames)).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (2).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (64000).to_bytes(4, "little")
        + (4).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(frames).to_bytes(4, "little")
        + frames
    )
    spoken = run_matrix.output_facts(wav, "voice")
    assert (spoken["sample_rate"], spoken["channels"], spoken["seconds"]) == (16000, 2, 1.0)

    sound = box(b"moov", box(b"trak", box(b"mdia", handler_box(b"soun"))))
    silent = box(b"moov", box(b"trak", box(b"mdia", handler_box(b"vide"))))
    assert run_matrix.output_facts(sound, "video")["audio_track"] is True
    assert run_matrix.output_facts(silent, "video")["audio_track"] is False


def test_a_video_with_no_track_is_not_credited_with_sound_because_the_word_appears():
    """`soun` sits in metadata, in a thumbnail or in a payload. A search for those four
    bytes answered yes to a file with no audio stream at all."""
    payload = box(b"ftyp", b"isom") + box(b"mdat", b"soun")

    assert run_matrix.output_facts(payload, "video")["audio_track"] is False


def test_a_truncated_video_is_not_credited_with_a_track_it_does_not_hold():
    whole = box(b"moov", box(b"trak", box(b"mdia", handler_box(b"soun"))))

    assert run_matrix.output_facts(whole[: len(whole) // 2], "video")["audio_track"] is False


def test_a_wav_with_a_metadata_chunk_before_the_audio_is_read_by_its_chunks():
    """A search for `data` finds the word in a LIST block before the samples, and the
    seconds then come from whatever number follows it."""
    frames = b"\x00" * 32000
    wav = (
        b"RIFF"
        + (0).to_bytes(4, "little")
        + b"WAVE"
        + chunk(b"LIST", b"INFOdata" + (999999).to_bytes(4, "little"))
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + len(frames).to_bytes(4, "little")
        + frames
    )

    facts = run_matrix.output_facts(wav, "music")

    assert (facts["sample_rate"], facts["channels"], facts["seconds"]) == (16000, 1, 1.0)


def test_a_truncated_wav_reports_no_seconds_rather_than_the_size_it_claims():
    wav = (
        b"RIFF"
        + (0).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (64000).to_bytes(4, "little")
    )

    assert run_matrix.output_facts(wav, "voice")["seconds"] == 0


def test_a_truncated_png_reports_no_size():
    head = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (640).to_bytes(4, "big") + (480).to_bytes(4, "big")

    assert "width" not in run_matrix.output_facts(head, "image")


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


def test_a_row_from_another_campaign_is_not_counted_as_coverage(tmp_path, monkeypatch, capsys):
    """The table says `other campaign` and the coverage count has to agree with it, or a
    stale success reads as a finished case."""
    case = {"id": "qwen21_turbo/generate/one", "kind": "image", "machines": {"mlx": {}, "cuda": {}}}
    (tmp_path / "matrix.jsonl").write_text(json.dumps(case) + "\n")
    manifest = {"git": "abc", "assets": {}}
    for machine in ("mlx", "cuda"):
        (tmp_path / f"campaign-{machine}.json").write_text(json.dumps(manifest))
    row = {
        "id": case["id"],
        "status": "succeeded",
        "fingerprint": run_matrix.fingerprint(case, manifest),
        "active": 1.0,
    }
    for machine in ("mlx", "cuda"):
        folder = tmp_path / "results" / machine
        folder.mkdir(parents=True)
        (folder / "one.bin").write_bytes(f"{machine} bytes".encode())
        row.update(file=f"results/{machine}/one.bin", sha256=run_matrix.sha256(f"{machine} bytes".encode()))
        (tmp_path / f"results-{machine}.jsonl").write_text(json.dumps(row) + "\n")
    stale = {
        "id": case["id"],
        "status": "succeeded",
        "fingerprint": "old",
        "active": 1.0,
        "file": "results/cuda/one.bin",
        "sha256": run_matrix.sha256(b"cuda bytes"),
    }
    (tmp_path / "results-cuda.jsonl").write_text(json.dumps(stale) + "\n")
    monkeypatch.setattr(sys, "argv", ["report.py", "--work", str(tmp_path)])

    assert report.main() == 0

    printed = capsys.readouterr().out
    assert "0 of 1 cases succeeded on both engines" in printed
    assert "1.0" in printed and "other campaign" in printed


def test_a_stale_or_failed_warm_row_does_not_hide_a_good_cold_row():
    base = {"status": "succeeded", "fingerprint": "now", "active": 3.0}
    warm = {"status": "succeeded", "fingerprint": "now", "active": 2.0}

    assert report.pick(base, warm, "now") is warm
    assert report.pick(base, {"status": "succeeded", "fingerprint": "old"}, "now") is base
    assert report.pick(base, {"status": "failed", "fingerprint": "now"}, "now") is base
    assert report.pick(base, None, "now") is base


def test_the_job_span_starts_when_the_studio_started_the_job():
    """The accept time is when a queued job began waiting. The studio's own timestamps say
    when it began running, and that is the figure two machines compare."""
    assert run_matrix.durations({"started_at": 110.0, "finished_at": 130.0}, 100.0, 131.0) == {
        "queue_wait": 10.0,
        "active": 20.0,
    }
    assert run_matrix.durations({"started_at": 110.0}, 100.0, 131.0) == {"queue_wait": 10.0, "active": 21.0}
    assert run_matrix.durations({"status": "succeeded"}, 100.0, 131.0) == {"active": 31.0}


def offered(workspace, backend_id):
    return {"backend": backend_id, "precision": "fp8" if workspace == "video" else ""}


def test_the_campaign_identity_changes_with_the_models_the_studio_serves():
    case = one_case()
    fast = run_matrix.campaign_manifest(
        "mlx", {}, run_matrix.live_configuration({"studio": {"image": {"backends": [{"id": "a"}]}}}, offered)
    )
    full = run_matrix.campaign_manifest(
        "mlx", {}, run_matrix.live_configuration({"studio": {"image": {"backends": [{"id": "b"}]}}}, offered)
    )

    assert run_matrix.fingerprint(case, fast) != run_matrix.fingerprint(case, full)


def test_the_live_configuration_leaves_out_the_parts_that_move():
    """The active selection and the resident list change as a campaign runs. A fingerprint
    that held either would refuse a campaign its own resume."""
    state = {
        "studio": {
            "image": {"active": "a", "backends": [{"id": "a"}, {"id": "b"}], "capabilities": {"sizes": ["512"]}},
            "memory": {"policy": "boundary", "boundary_gib": 40, "resident": ["a"]},
        }
    }

    live = run_matrix.live_configuration(state, offered)

    assert live["memory_policy"] == "boundary"
    assert live["memory_boundary_gib"] == 40
    assert "resident" not in json.dumps(live)
    assert "active" not in json.dumps(live)
    assert sorted(live["offered"]) == ["image/a", "image/b"]

    moved = json.loads(json.dumps(state))
    moved["studio"]["image"]["active"] = "b"
    assert run_matrix.live_configuration(moved, offered) == live


def test_a_changed_tree_is_not_recorded_as_clean(monkeypatch):
    monkeypatch.setattr(run_matrix.subprocess, "run", Mock(return_value=SimpleNamespace(stdout=" M studio/x.py\n")))

    assert run_matrix.git_dirty() is True


def test_a_tree_whose_state_cannot_be_read_is_not_called_clean(monkeypatch):
    monkeypatch.setattr(run_matrix.subprocess, "run", Mock(side_effect=OSError("no git")))

    assert run_matrix.git_dirty() == "unknown"


def test_a_case_that_throws_always_stops_its_memory_sampler(work, monkeypatch):
    stopped = []

    class Sampler:
        def start(self):
            pass

        def finish(self):
            stopped.append(True)
            return {}

    def explode(*_):
        raise RuntimeError("the studio went away")

    monkeypatch.setattr(run_matrix, "MemorySampler", Sampler)
    monkeypatch.setattr(run_matrix, "_drive", explode)
    with served() as studio, pytest.raises(RuntimeError, match="the studio went away"):
        run(studio, work, one_case(), monkeypatch)

    assert stopped == [True]


@pytest.mark.parametrize("value", ["nan", "inf", "-1"])
def test_a_deadline_that_is_not_finite_and_positive_stops_the_run(tmp_path, monkeypatch, value):
    monkeypatch.setattr(
        sys, "argv", ["run_matrix.py", "--machine", "mlx", "--work", str(tmp_path), "--deadline", value]
    )

    with pytest.raises(SystemExit, match="zero or more seconds"):
        run_matrix.main()


def test_a_build_that_dies_leaves_the_old_assets_and_manifest_alone(tmp_path, monkeypatch):
    """Assembling beside the set in use is what makes a failed build cheap: the previous
    fixtures and the manifest that describes them are still there, and nothing else is."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "music-10s.wav").write_bytes(b"old")
    (tmp_path / "assets.sha256").write_text("0  music-10s.wav\n")
    before = (tmp_path / "assets.sha256").read_text()

    def half_a_build(_base, _body, name, target, _deadline):
        (target / name).write_bytes(b"new")
        raise SystemExit("stop here")

    monkeypatch.setattr(build_assets, "run", half_a_build)
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_assets.py", "--work", str(tmp_path), "--image-backend", "a", "--voice-backend", "b", "--force"],
    )

    with pytest.raises(SystemExit, match="stop here"):
        build_assets.main()

    assert (tmp_path / "assets" / "music-10s.wav").read_bytes() == b"old"
    assert [one.name for one in (tmp_path / "assets").iterdir()] == ["music-10s.wav"]
    assert (tmp_path / "assets.sha256").read_text() == before


def test_a_build_swaps_in_the_whole_new_set(tmp_path, monkeypatch):
    """The new set replaces the old one only once it is complete, and the manifest that
    names it goes in with it."""
    from PIL import Image

    def fake_run(_base, _body, name, target, _deadline):
        if name == "picture-1024.png":
            Image.new("RGB", (1024, 1024), (10, 20, 30)).save(target / name)
        else:
            (target / name).write_bytes(name.encode())
        return target / name

    monkeypatch.setattr(build_assets, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_assets.py", "--work", str(tmp_path), "--image-backend", "a", "--voice-backend", "b"],
    )

    assert build_assets.main() == 0

    assets = tmp_path / "assets"
    assert (assets / "picture-1024.png").is_file()
    assert (assets / "voice-short.wav").read_bytes() == b"voice-short.wav"
    assert (assets / "scripts.json").is_file()
    assert not (tmp_path / "assets.new").exists()
    listed = (tmp_path / "assets.sha256").read_text().splitlines()
    assert len(listed) == len(list(assets.iterdir()))
    assert all(line.split("  ")[1] in {one.name for one in assets.iterdir()} for line in listed)


def test_a_torn_last_line_keeps_the_rows_before_it(work):
    """The runner appends one line per trial. A process that dies mid-append must not cost
    the campaign every completed row it had."""
    path = work / "results-mlx.jsonl"
    path.write_text(json.dumps({"id": "a"}) + "\n" + json.dumps({"id": "b"}) + "\n" + '{"id": "c"')

    assert [record["id"] for record in run_matrix.rows(path)] == ["a", "b"]


def test_a_bad_line_before_the_end_stops_the_run(work):
    path = work / "results-mlx.jsonl"
    path.write_text(json.dumps({"id": "a"}) + "\n{broken\n" + json.dumps({"id": "c"}) + "\n")

    with pytest.raises(SystemExit, match="is not a record"):
        run_matrix.rows(path)


def test_two_case_ids_that_slug_alike_keep_two_checkpoints(work):
    first = run_matrix.checkpoint_path(work, "mlx", "a/b")
    second = run_matrix.checkpoint_path(work, "mlx", "a_b")

    assert first != second
    assert first.name.startswith("a_b-") and second.name.startswith("a_b-")


def test_a_corrupt_checkpoint_costs_a_rerun_not_the_campaign(work, capsys):
    path = work / "phases-mlx" / "one.json"
    path.parent.mkdir()
    path.write_text("{not json")

    assert run_matrix.read_checkpoint(path, "fp") == {}
    assert "runs again" in capsys.readouterr().out


def test_a_repeat_trial_keeps_both_artifacts(work, monkeypatch):
    """The same case and fingerprint, two runs, two sets of bytes. The second must not
    overwrite the first, or the earlier row points at media it never produced."""
    case = one_case()
    with served() as studio:
        studio.bodies = [b"first", b"second"]
        first = run(studio, work, case, monkeypatch, force=True)
        second = run(studio, work, case, monkeypatch, force=True)

    assert first["file"] != second["file"]
    assert (work / first["file"]).read_bytes() == b"first"
    assert (work / second["file"]).read_bytes() == b"second"
    assert run_matrix.saved(work, first) and run_matrix.saved(work, second)


def report_work(tmp_path, row_overrides=None, warm=None):
    """A work directory the report can read: one image case, one campaign, two machines."""
    case = {"id": "qwen21_turbo/generate/one", "kind": "image", "machines": {"mlx": {}, "cuda": {}}}
    (tmp_path / "matrix.jsonl").write_text(json.dumps(case) + "\n")
    manifest = {"git": "abc", "assets": {}}
    for machine in ("mlx", "cuda"):
        (tmp_path / f"campaign-{machine}.json").write_text(json.dumps(manifest))
    expected = run_matrix.fingerprint(case, manifest)
    for machine in ("mlx", "cuda"):
        folder = tmp_path / "results" / machine
        folder.mkdir(parents=True)
        (folder / "one.bin").write_bytes(f"{machine} bytes".encode())
        row = {
            "id": case["id"],
            "status": "succeeded",
            "fingerprint": expected,
            "active": 1.0,
            "file": f"results/{machine}/one.bin",
            "sha256": run_matrix.sha256(f"{machine} bytes".encode()),
        }
        row.update(row_overrides or {})
        (tmp_path / f"results-{machine}.jsonl").write_text(json.dumps(row) + "\n")
        if warm is not None:
            warm_row = {**row, **warm}
            (tmp_path / f"warm-{machine}.jsonl").write_text(json.dumps(warm_row) + "\n")
    return expected


def test_a_case_whose_media_is_gone_is_not_counted_as_coverage(tmp_path, monkeypatch, capsys):
    """The runner will not skip a case whose artifact is missing. The report must not count
    one either, or a copied campaign prints a full table nobody can inspect."""
    report_work(tmp_path)
    monkeypatch.setattr(sys, "argv", ["report.py", "--work", str(tmp_path)])

    assert report.main() == 0
    assert "1 of 1 cases succeeded on both engines with their media" in capsys.readouterr().out

    (tmp_path / "results" / "mlx" / "one.bin").unlink()

    assert report.main() == 0
    printed = capsys.readouterr().out
    assert "0 of 1 cases succeeded on both engines with their media" in printed
    assert "mlx (no media)" in printed
    assert "1 of 1 succeeded by status alone" in printed
    assert "| no media |" in printed


def test_a_failed_warm_trial_is_listed_even_when_the_cold_row_succeeded(tmp_path, monkeypatch, capsys):
    """Survivorship bias hides the trial that went wrong, which is the one worth seeing."""
    report_work(tmp_path, warm={"status": "failed", "error": "the engine stopped"})
    monkeypatch.setattr(sys, "argv", ["report.py", "--work", str(tmp_path)])

    assert report.main() == 0

    printed = capsys.readouterr().out
    assert "warm trials did not succeed" in printed
    assert "the engine stopped" in printed
    assert "1 of 1 cases succeeded on both engines with their media" in printed


def test_strict_reports_a_failed_case_in_its_exit_status(work, monkeypatch):
    (work / "matrix.jsonl").write_text(json.dumps(one_case()) + "\n")
    with served(final="failed") as studio:
        monkeypatch.setattr(
            sys,
            "argv",
            ["run_matrix.py", "--machine", "mlx", "--base", studio.base, "--work", str(work), "--strict"],
        )
        assert run_matrix.main() == 1
    with served(final="failed") as studio:
        monkeypatch.setattr(
            sys,
            "argv",
            ["run_matrix.py", "--machine", "mlx", "--base", studio.base, "--work", str(work)],
        )
        assert run_matrix.main() == 0


def test_a_studio_running_another_commit_is_refused(work, monkeypatch):
    """The runner reads its own checkout. If the studio serves another commit, a figure
    from it would be attributed to code nobody measured."""
    (work / "matrix.jsonl").write_text(json.dumps(one_case()) + "\n")
    monkeypatch.setattr(run_matrix, "git_sha", lambda: "runner-sha")
    with served() as studio:
        studio.build = {"commit": "another-sha", "dirty": False}
        monkeypatch.setattr(
            sys, "argv", ["run_matrix.py", "--machine", "mlx", "--base", studio.base, "--work", str(work)]
        )

        with pytest.raises(SystemExit, match="would be attributed"):
            run_matrix.main()


def test_the_report_names_its_columns(tmp_path, monkeypatch, capsys):
    """Two machines produced the reference page. The runner is generic, so a column can be
    named without editing the script before another machine's campaign is printed."""
    report_work(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["report.py", "--work", str(tmp_path), "--label", "mlx=MacBook", "--label", "cuda=Spark"]
    )

    report.main()

    assert "| Case | MacBook (s) | Spark (s) |" in capsys.readouterr().out


def test_a_label_that_names_no_machine_is_refused(tmp_path, monkeypatch):
    report_work(tmp_path)
    monkeypatch.setattr(sys, "argv", ["report.py", "--work", str(tmp_path), "--label", "mac=MacBook"])

    with pytest.raises(SystemExit, match="MACHINE=TEXT"):
        report.main()
