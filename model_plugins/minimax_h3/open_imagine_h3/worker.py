"""Adapt the pinned staged runner to private, cancellable in-memory transport.

The engine keeps its own loading, sampling and decoding. This adapter replaces its
metrics writer and media writer, and forwards only numerical progress and memory metrics.
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import the H3 runtime module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ProgressSink(io.TextIOBase):
    def __init__(self, emit):
        self.emit = emit

    def write(self, text):
        match = re.match(r"^step ([1-8])/8: [0-9.]+s(?: |$)", text)
        if match:
            self.emit({"event": "step", "step": int(match[1]), "total": 8})
        return len(text)

    def flush(self):
        pass


def render(engine, models, request, emit):
    media = load_module(Path(__file__).with_name("media.py"), "_open_imagine_h3_media")
    media.check_tools()
    original = engine.Recorder
    encoded = None
    streams = []

    class MemoryRecorder(original):
        def flush(self):
            pass

        @contextlib.contextmanager
        def phase(self, name):
            with super().phase(name):
                yield
            item = self.data["phases"][-1]
            emit({"event": "phase", "phase": name, "seconds": item["seconds"], "peak_gib": item["peak_gib"]})

    def save(_path, video, fps, audio, sample_rate, *, crf, **_options):
        nonlocal encoded, streams
        encoded = media.encode_mp4(video, fps, audio, sample_rate, crf=crf)
        streams = media.inspect_mp4(encoded)
        picture = next(stream for stream in streams if stream["codec_type"] == "video")
        sound = next(stream for stream in streams if stream["codec_type"] == "audio")
        if (
            picture["width"] != request["width"]
            or picture["height"] != request["height"]
            or int(picture["nb_read_packets"]) != request["frames"]
            or int(sound["sample_rate"]) != 32000
            or sound["channels"] != 2
        ):
            raise RuntimeError("H3 output does not match its requested geometry or soundtrack.")

    def count(_path):
        return next(int(stream["nb_read_packets"]) for stream in streams if stream["codec_type"] == "video")

    engine.Recorder = MemoryRecorder
    engine.save_mp4 = save
    engine.probe_video_frames = count
    previous_argv = sys.argv
    sys.argv = [
        "h3-studio-worker",
        "--dit",
        str(models / "h3-dit-q8"),
        "--compact-root",
        str(models / "ddalcu-q8"),
        "--text-config",
        str(models / "upstream-meta" / "FL2VA" / "text_encoder" / "config.json"),
        "--width",
        str(request["width"]),
        "--height",
        str(request["height"]),
        "--frames",
        str(request["frames"]),
        "--seed",
        str(request["seed"]),
        "--steps",
        "9",
        "--wired-gb",
        "40",
        "--memory-gb",
        "48",
        "--metrics",
        os.devnull,
        "--output",
        os.devnull,
        "--",
        request["prompt"],
    ]
    try:
        with contextlib.redirect_stdout(ProgressSink(emit)), contextlib.redirect_stderr(io.StringIO()):
            code = engine.main()
        if code != 0 or encoded is None:
            raise RuntimeError("H3 did not finish a clip.")
        return encoded
    finally:
        sys.argv = previous_argv


def main():
    # Keep private data out of diagnostics, including native libraries that write to file descriptors.
    output = os.fdopen(os.dup(1), "wb", buffering=0)
    events = os.fdopen(os.dup(2), "w", buffering=1)
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)

    def emit(event):
        events.write(json.dumps(event) + "\n")

    try:
        engine_dir, models = map(Path, sys.argv[1:])
        pin = runpy.run_path(str(Path(__file__).with_name("runtime.py")))["ENGINE_COMMIT"]
        head = subprocess.run(
            ["git", "-C", str(engine_dir), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        clean = subprocess.run(["git", "-C", str(engine_dir), "diff", "--quiet", "HEAD"], capture_output=True)
        if head.stdout.strip() != pin or clean.returncode:
            raise RuntimeError("The H3 engine must match its pinned source.")
        request = json.load(sys.stdin)
        engine = load_module(engine_dir / "scripts" / "generate_staged.py", "_open_imagine_h3_engine")
        output.write(render(engine, models, request, emit))
        return 0
    except BaseException as error:
        emit({"event": "error", "type": type(error).__name__})
        return 1
    finally:
        output.close()
        events.close()


if __name__ == "__main__":
    raise SystemExit(main())
