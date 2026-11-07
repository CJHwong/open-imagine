"""Adapt the pinned staged runner to private, cancellable in-memory transport.

The engine keeps its own loading, sampling and decoding. This adapter replaces its
metrics writer and media writer, and forwards only numerical progress and memory metrics.
It also hands the engine its keyframes and its audio track from memory. The engine reads
them in three places: a file check, `Image.open` and `read_audio`. Each one sees a path
under MEMORY, which does not exist on disk, so a read that bypasses them fails.

A LoRA is a file on disk, which the engine reads itself. The engine only prints a warning
when it cannot apply all of one, and that text goes nowhere, so this adapter reads the
engine's own count instead and stops the run before the denoise.
"""

import base64
import contextlib
import importlib.util
import io
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path, PosixPath

MEMORY = Path("/open-imagine-memory")
TRACK = str(MEMORY / "track")


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
    from PIL import Image, ImageOps

    read_image = Image.open
    stills = {}
    flags = []
    for index, keyframe in enumerate(request.get("keyframes", ())):
        path = str(MEMORY / f"{index}.png")
        with Image.open(io.BytesIO(base64.b64decode(keyframe["png"]))) as image:
            # Cover-crop every still to the canvas here. The engine then uses each one as it is,
            # and the first frame is not stretched, which the engine does to a first frame.
            size = (request["width"], request["height"])
            stills[path] = ImageOps.fit(image.convert("RGB"), size, Image.Resampling.LANCZOS)
        if keyframe["frame"] == 0:
            flags += ["--first-frame", path]
        else:
            flags += ["--keyframe", f"{path}@{keyframe['frame']}"]
    track = base64.b64decode(request["audio"]) if request.get("audio") else None
    if track is not None:
        flags += ["--audio-drive", TRACK]
    # Runtime adapters on the Q8 layers, in the order picked. The engine stacks them.
    for lora in request.get("loras", ()):
        flags += ["--lora", f"{lora['path']}:{lora['scale']}"]

    held = set(stills) | ({TRACK} if track is not None else set())

    class MemoryPath(PosixPath):
        def is_file(self, *args, **kwargs):
            return str(self) in held or super().is_file(*args, **kwargs)

    def open_image(source, *args, **kwargs):
        if str(source) in stills:
            return stills[str(source)].copy()
        return read_image(source, *args, **kwargs)

    def read_audio(path, sample_rate=32000, start_seconds=0.0, duration_seconds=None):
        if track is None or str(path) != TRACK:
            raise RuntimeError("H3 reads only the audio track it was given.")
        # The engine reads the track from its start to its end. A clip uses its first seconds,
        # so a long track is not decoded whole.
        seconds = request["frames"] / 24 + 1
        if duration_seconds is not None:
            seconds = min(seconds, duration_seconds)
        return media.decode_audio(track, sample_rate, start_seconds, seconds)

    original = engine.Recorder
    encoded = None
    streams = []

    class MemoryRecorder(original):
        unfit = False

        def flush(self):
            # The engine counts each LoRA's layers once it has applied them, before the denoise.
            # A LoRA that it applied in part, or not at all, still renders a plausible clip.
            # The phase that raised flushes once more on its way out, so report only once.
            accounting = self.data.get("lora_accounting")
            for index, adapter in enumerate(accounting["adapters"] if accounting and not self.unfit else ()):
                applied, unaccounted = int(adapter["applied"] or 0), int(adapter["unaccounted"])
                if not applied or unaccounted:
                    self.unfit = True
                    emit({"event": "lora_unfit", "index": index, "applied": applied, "unaccounted": unaccounted})
                    raise RuntimeError("H3 cannot apply all of a LoRA.")

        @contextlib.contextmanager
        def phase(self, name):
            # The check above needs the engine's count. Without it, a LoRA goes unchecked, so stop.
            if name == "joint_denoise" and request.get("loras") and "lora_accounting" not in self.data:
                raise RuntimeError("H3 did not count the layers of the LoRAs.")
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
    engine.Path = MemoryPath
    engine.read_audio = read_audio
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
        *flags,
        "--",
        request["prompt"],
    ]
    Image.open = open_image  # ty: ignore[invalid-assignment]
    try:
        with contextlib.redirect_stdout(ProgressSink(emit)), contextlib.redirect_stderr(io.StringIO()):
            code = engine.main()
        if code != 0 or encoded is None:
            raise RuntimeError("H3 did not finish a clip.")
        return encoded
    finally:
        sys.argv = previous_argv
        Image.open = read_image


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
