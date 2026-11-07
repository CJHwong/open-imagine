import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from open_imagine_h3 import worker
from open_imagine_h3.runtime import ENGINE_COMMIT


@pytest.fixture
def fake_engine(media_tools):
    class Recorder:
        def __init__(self, path, settings):
            self.path = path
            self.data = {"settings": settings, "phases": []}
            self.flush()

        def flush(self):
            raise AssertionError("private metrics reached a disk writer")

        @contextlib.contextmanager
        def phase(self, name):
            yield
            self.data["phases"].append({"seconds": 1, "peak_gib": 2})
            self.flush()

    engine = SimpleNamespace(Recorder=Recorder)

    def main():
        import sys

        assert sys.argv[-2:] == ["--", "private test words"]
        assert "--prompt-cache" not in sys.argv and "--draft-cache-dir" not in sys.argv
        record = engine.Recorder(Path("must-not-write.json"), {"prompt": sys.argv[-1]})
        with record.phase("joint_denoise"):
            print("private test words")
            print("step 1/8: 0.1s (active 2.0 GiB)", flush=True)
        engine.save_mp4(None, np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 7000)), 32000, crf=18)
        assert engine.probe_video_frames(None) == 5
        return 0

    engine.main = main
    return engine


def request(**changes):
    return dict(prompt="private test words", width=32, height=32, frames=5, seed=7, **changes)


def test_worker_uses_memory_metrics_and_media_and_emits_only_safe_events(fake_engine, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    events = []

    data = worker.render(fake_engine, tmp_path, request(), events.append)

    assert data[4:8] == b"ftyp"
    assert events == [
        {"event": "step", "step": 1, "total": 8},
        {"event": "phase", "phase": "joint_denoise", "seconds": 1, "peak_gib": 2},
    ]
    assert "private" not in json.dumps(events) + capsys.readouterr().out
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("code", [0, 1])
def test_worker_refuses_success_without_a_clip(fake_engine, tmp_path, code):
    fake_engine.main = lambda: code

    with pytest.raises(RuntimeError, match="did not finish"):
        worker.render(fake_engine, tmp_path, request(), lambda _: None)


def test_worker_refuses_a_clip_that_does_not_match_the_request(fake_engine, tmp_path):
    payload = request()
    payload["width"] = 64

    with pytest.raises(RuntimeError, match="does not match"):
        worker.render(fake_engine, tmp_path, payload, lambda _: None)


def test_worker_rejects_unimportable_runtime_modules(tmp_path):
    with pytest.raises(RuntimeError, match="Cannot import"):
        worker.load_module(tmp_path / "unknown.extension", "_h3_bad_fixture")


@pytest.mark.parametrize(
    "dirty,head,malformed",
    [
        (True, ENGINE_COMMIT, False),
        (False, "wrong", False),
        (False, ENGINE_COMMIT, True),
        (False, ENGINE_COMMIT, False),
    ],
)
def test_worker_main_checks_the_pin_and_sanitizes_failures(fake_engine, tmp_path, monkeypatch, dirty, head, malformed):
    class Bytes(io.BytesIO):
        def close(self):
            pass

    class Text(io.StringIO):
        def close(self):
            pass

    output, events = Bytes(), Text()
    monkeypatch.setattr(worker.os, "dup", lambda fd: fd)
    monkeypatch.setattr(worker.os, "dup2", lambda *_: None)
    monkeypatch.setattr(worker.os, "fdopen", lambda fd, *_args, **_kw: output if fd == 1 else events)
    monkeypatch.setattr(worker.sys, "argv", ["worker", str(tmp_path / "engine"), str(tmp_path / "models")])
    monkeypatch.setattr(
        worker.sys, "stdin", io.StringIO("invalid private words" if malformed else json.dumps(request()))
    )
    monkeypatch.setattr(
        worker.subprocess, "run", lambda command, **_: SimpleNamespace(stdout=head, returncode=int(dirty))
    )
    load = worker.load_module
    monkeypatch.setattr(
        worker, "load_module", lambda path, name: fake_engine if name.endswith("engine") else load(path, name)
    )
    monkeypatch.setattr(worker, "render", lambda *_: b"\0\0\0\x18ftypisom")

    code = worker.main()

    assert "private" not in events.getvalue()
    if dirty or head != ENGINE_COMMIT or malformed:
        assert code == 1 and not output.getvalue()
        assert json.loads(events.getvalue())["event"] == "error"
    else:
        assert code == 0 and output.getvalue()[4:8] == b"ftyp"


def test_progress_sink_discards_arbitrary_engine_text():
    events = []
    sink = worker.ProgressSink(events.append)
    text = "private words\nstep 1/8: 0.1s"
    assert sink.write(text) == len(text)
    sink.write("step 8/8: 2.3s")
    sink.flush()
    assert events == [{"event": "step", "step": 8, "total": 8}]


def test_worker_passes_option_like_text_as_a_literal_prompt(fake_engine, tmp_path):
    import argparse
    import sys

    class Parsed(Exception):
        pass

    def parse():
        parser = argparse.ArgumentParser()
        parser.add_argument("prompt")
        for flag in (
            "dit",
            "compact-root",
            "text-config",
            "width",
            "height",
            "frames",
            "seed",
            "steps",
            "wired-gb",
            "memory-gb",
            "metrics",
            "output",
        ):
            parser.add_argument("--" + flag)
        assert parser.parse_args(sys.argv[1:]).prompt == "--chain-prompts=literal_text"
        raise Parsed

    fake_engine.main = parse
    payload = request()
    payload["prompt"] = "--chain-prompts=literal_text"

    with pytest.raises(Parsed):
        worker.render(fake_engine, tmp_path, payload, lambda _: None)


def test_worker_script_entrypoint_refuses_bad_arguments_without_exposing_input(monkeypatch):
    import runpy

    events = []
    monkeypatch.setattr(worker.os, "dup", lambda fd: fd)
    monkeypatch.setattr(worker.os, "dup2", lambda *_: None)
    monkeypatch.setattr(
        worker.os, "fdopen", lambda *_args, **_kw: SimpleNamespace(write=events.append, close=lambda: None)
    )
    monkeypatch.setattr(worker.sys, "argv", ["worker"])

    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(worker.__file__, run_name="__main__")

    assert stopped.value.code == 1
    assert json.loads(events[0]) == {"event": "error", "type": "ValueError"}
