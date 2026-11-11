import argparse
import base64
import contextlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from studio.l3_interface_adapters.gateways.video.minimax_h3 import worker
from studio.l3_interface_adapters.gateways.video.minimax_h3.runtime import ENGINE_COMMIT


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
            # As the engine's own: a phase records itself and flushes, also when it raised.
            try:
                yield
            finally:
                self.data["phases"].append({"seconds": 1, "peak_gib": 2})
                self.flush()

    engine = SimpleNamespace(Recorder=Recorder)

    def main():
        assert sys.argv[-2:] == ["--", "private test words"]
        assert "--prompt-cache" not in sys.argv and "--draft-cache-dir" not in sys.argv
        assert not {"--first-frame", "--keyframe", "--audio-drive", "--lora"} & set(sys.argv)
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
    opener = Image.open

    with pytest.raises(RuntimeError, match="did not finish"):
        worker.render(fake_engine, tmp_path, request(), lambda _: None)

    assert Image.open is opener


def png(width, height, colours):
    """A still of equal vertical bands, one per colour."""
    image = Image.new("RGB", (width, height))
    band = width // len(colours)
    for index, colour in enumerate(colours):
        image.paste(colour, (index * band, 0, (index + 1) * band, height))
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


def test_worker_hands_keyframes_and_the_track_to_the_engine_from_memory(fake_engine, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    red, green, blue = (255, 0, 0), (0, 255, 0), (0, 0, 255)
    seen = {}

    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument("--first-frame")
        parser.add_argument("--keyframe", action="append")
        parser.add_argument("--audio-drive")
        args, _ = parser.parse_known_args(sys.argv[1:])
        held = [args.first_frame, *(spec.rpartition("@")[0] for spec in args.keyframe), args.audio_drive]
        assert all(fake_engine.Path(path).is_file() for path in held)
        assert not fake_engine.Path(str(worker.MEMORY / "other.png")).is_file()
        assert fake_engine.Path(__file__).is_file()
        with pytest.raises(FileNotFoundError):
            Path(args.first_frame).read_bytes()
        seen["first"] = Image.open(args.first_frame).convert("RGB")
        seen["keyframes"] = [
            (Image.open(spec.rpartition("@")[0]).size, spec.rpartition("@")[2]) for spec in args.keyframe
        ]
        seen["other"] = Image.open(io.BytesIO(png(4, 4, [blue]))).size
        seen["audio"] = fake_engine.read_audio(fake_engine.Path(args.audio_drive), start_seconds=0.0)
        seen["window"] = fake_engine.read_audio(args.audio_drive, 32000, 0.0, 0.5)
        with pytest.raises(RuntimeError, match="only the audio track"):
            fake_engine.read_audio("/elsewhere/track.wav")
        fake_engine.save_mp4(None, np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 7000)), 32000, crf=18)
        return 0

    opener = Image.open
    fake_engine.main = main
    payload = request(
        keyframes=[
            {"frame": 0, "png": base64.b64encode(png(96, 32, [red, green, blue])).decode()},
            {"frame": 2, "png": base64.b64encode(png(32, 32, [red])).decode()},
            {"frame": 4, "png": base64.b64encode(png(64, 64, [blue])).decode()},
        ],
        audio=base64.b64encode(b"\0" * 3000).decode(),
    )

    worker.render(fake_engine, tmp_path, payload, lambda _: None)

    first = np.asarray(seen["first"])
    assert seen["first"].size == (32, 32) and (first[:, :, 1] > 200).all() and (first[:, :, [0, 2]] < 60).all()
    assert seen["keyframes"] == [((32, 32), "2"), ((32, 32), "4")]
    assert seen["other"] == (4, 4)
    assert seen["audio"].shape == (2, round((5 / 24 + 1) * 32000))
    assert seen["window"].shape == (2, 16000)
    assert Image.open is opener
    assert not list(tmp_path.iterdir())


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
    monkeypatch.setattr(worker.sys, "path", list(sys.path))
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

    # The engine is a checkout, not a package, so its directory comes first on the path.
    assert sys.path[0] == str(tmp_path / "engine")
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


@pytest.mark.parametrize("line", ["step 4/8: 0.1s", "step 0/4: 0.1s", "step 5/4: 0.1s", "step 12/12: 0.1s"])
def test_progress_sink_reports_only_the_steps_of_its_own_schedule(line):
    events = []
    sink = worker.ProgressSink(events.append, 4)
    sink.write(line)
    sink.write("step 4/4: 2.3s")
    assert events == [{"event": "step", "step": 4, "total": 4}]


@pytest.mark.parametrize("changes,points", [({}, "9"), ({"forwards": 8}, "9"), ({"forwards": 4}, "5")])
def test_worker_runs_the_number_of_forwards_that_the_request_names(fake_engine, tmp_path, changes, points):
    seen = {}

    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument("--steps")
        args, _ = parser.parse_known_args(sys.argv[1:])
        seen["steps"] = args.steps
        print(f"step 1/{int(args.steps) - 1}: 0.1s", flush=True)
        fake_engine.save_mp4(None, np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 7000)), 32000, crf=18)
        return 0

    fake_engine.main = main
    events = []

    worker.render(fake_engine, tmp_path, request(**changes), events.append)

    # The engine counts sigma points, one more than the forwards that progress reports.
    assert seen == {"steps": points}
    assert events == [{"event": "step", "step": 1, "total": int(points) - 1}]


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


def test_worker_hands_each_lora_to_the_engine_in_the_order_picked(fake_engine, tmp_path):
    seen = {}

    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument("--lora", action="append")
        args, _ = parser.parse_known_args(sys.argv[1:])
        seen["loras"] = args.lora
        fake_engine.save_mp4(None, np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 7000)), 32000, crf=18)
        return 0

    fake_engine.main = main
    loras = [{"path": "/loras/one.safetensors", "scale": 0.4}, {"path": "/lo:ras/two.safetensors", "scale": 1.0}]

    worker.render(fake_engine, tmp_path, request(loras=loras), lambda _: None)

    assert seen["loras"] == ["/loras/one.safetensors:0.4", "/lo:ras/two.safetensors:1.0"]
    # The engine's parse_spec splits PATH:SCALE at the last colon, so a colon in the path is safe.
    assert [spec.rpartition(":")[::2] for spec in seen["loras"]] == [
        ("/loras/one.safetensors", "0.4"),
        ("/lo:ras/two.safetensors", "1.0"),
    ]


def accounting(*adapters):
    return {"adapters": [{"path": "private", "applied": applied, "unaccounted": lost} for applied, lost in adapters]}


@pytest.mark.parametrize(
    "adapters,index,applied,unaccounted",
    [
        (((0, 0),), 0, 0, 0),
        (((None, 0),), 0, 0, 0),
        (((100, 0), (208, 51)), 1, 208, 51),
    ],
)
def test_worker_stops_before_the_denoise_when_the_engine_cannot_apply_a_lora(
    fake_engine, tmp_path, adapters, index, applied, unaccounted
):
    def main():
        record = fake_engine.Recorder(Path("must-not-write.json"), {})
        with record.phase("adaln_cache_and_noise"):
            record.data["lora_accounting"] = accounting(*adapters)
            record.flush()
        raise AssertionError("the denoise started")

    fake_engine.main = main
    events = []

    with pytest.raises(RuntimeError, match="cannot apply all of a LoRA"):
        worker.render(fake_engine, tmp_path, request(), events.append)

    # The phase flushes again on its way out, and the gateway hears about the LoRA once.
    unfit = {"event": "lora_unfit", "index": index, "applied": applied, "unaccounted": unaccounted}
    assert events == [unfit]
    assert "private" not in json.dumps(events)


LORAS = [{"path": "/loras/one.safetensors", "scale": 0.4}, {"path": "/loras/two.safetensors", "scale": 1.0}]


def test_worker_runs_on_when_the_engine_applied_every_lora(fake_engine, tmp_path):
    def main():
        record = fake_engine.Recorder(Path("must-not-write.json"), {})
        record.data["lora_accounting"] = accounting((100, 0), (208, 0))
        record.flush()
        with record.phase("joint_denoise"):
            pass
        fake_engine.save_mp4(None, np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 7000)), 32000, crf=18)
        return 0

    fake_engine.main = main
    events = []

    assert worker.render(fake_engine, tmp_path, request(loras=LORAS), events.append)[4:8] == b"ftyp"
    assert events == [{"event": "phase", "phase": "joint_denoise", "seconds": 1, "peak_gib": 2}]


def test_worker_stops_before_the_denoise_when_the_engine_counted_no_lora(fake_engine, tmp_path):
    # A later engine pin can rename or move the count. The check above then has nothing to read.
    def main():
        record = fake_engine.Recorder(Path("must-not-write.json"), {})
        with record.phase("adaln_cache_and_noise"):
            pass
        with record.phase("joint_denoise"):
            raise AssertionError("the denoise started")

    fake_engine.main = main
    events = []

    with pytest.raises(RuntimeError, match="did not count the layers"):
        worker.render(fake_engine, tmp_path, request(loras=LORAS), events.append)

    assert events == [{"event": "phase", "phase": "adaln_cache_and_noise", "seconds": 1, "peak_gib": 2}]


def test_worker_runs_the_flash_pack_on_the_changed_engine(fake_engine, tmp_path, monkeypatch):
    seen = {}

    def load_module(path, name):
        assert path.name == "flash.py" and path.is_file()
        return SimpleNamespace(install=lambda engine: seen.setdefault("engine", engine) and ["--sampler", "euler"])

    def main():
        parser = argparse.ArgumentParser()
        for flag in ("--dit", "--steps", "--sampler"):
            parser.add_argument(flag)
        args, _ = parser.parse_known_args(sys.argv[1:])
        seen["args"] = (Path(args.dit).name, args.steps, args.sampler)
        assert sys.argv[-2:] == ["--", "private test words"]
        fake_engine.save_mp4(None, np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 7000)), 32000, crf=18)
        return 0

    fake_engine.main = main
    media = worker.load_module
    monkeypatch.setattr(
        worker, "load_module", lambda path, name: load_module(path, name) if "flash" in name else media(path, name)
    )

    worker.render(fake_engine, tmp_path, request(forwards=6, flash=True), lambda _: None)

    assert seen == {"engine": fake_engine, "args": ("h3-flash-dit-q8", "7", "euler")}


def test_worker_runs_the_base_pack_without_the_flash_changes(fake_engine, tmp_path):
    seen = {}

    def main():
        seen["argv"] = list(sys.argv)
        fake_engine.save_mp4(None, np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 7000)), 32000, crf=18)
        return 0

    fake_engine.main = main

    worker.render(fake_engine, tmp_path, request(flash=False), lambda _: None)

    assert str(tmp_path / "h3-dit-q8") in seen["argv"] and "--sampler" not in seen["argv"]
