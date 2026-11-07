"""Run one owned H3 child with input and output held in memory."""

import json
import secrets
import shutil
from pathlib import Path

from studio.plugins.video import Cancelled, InvalidJob, VideoBackendGateway, VideoResult

from .capabilities import CAPABILITIES
from .runtime import DEFAULT_ENGINE, DEFAULT_MODELS, MAX_RESULT_BYTES, weights_ready


class MinimaxH3BackendGateway(VideoBackendGateway):
    def __init__(self, context):
        self._context = context

    def capabilities(self):
        return CAPABILITIES

    def run(self, job, progress=None, cancelled=None):
        if cancelled and cancelled():
            raise Cancelled("H3 generation was cancelled.")
        if job.references or job.edit is not None or job.audio is not None or job.loras:
            raise InvalidJob("This H3 preview accepts text only.")
        if job.fast_mode or not job.include_audio:
            raise InvalidJob("This H3 preview uses its base schedule and includes sound.")
        if any(shutil.which(tool) is None for tool in ("ffmpeg", "ffprobe")):
            raise InvalidJob("Install ffmpeg and ffprobe before generating an H3 clip.")
        if (
            (job.width, job.height) not in {(shape.width, shape.height) for shape in CAPABILITIES.shapes}
            or not 73 <= job.num_frames <= 124
            or (job.num_frames - 5) % 17
            or job.frame_rate != 24
        ):
            raise InvalidJob("Choose an offered H3 size and a 73-124 frame clip at 24 fps.")
        if job.seed is not None and (type(job.seed) is not int or not 0 <= job.seed < 2**32):
            raise InvalidJob("Choose an H3 seed between 0 and 4294967295.")
        settings = self._context.settings
        engine = Path(settings.get("engine_dir", DEFAULT_ENGINE)).expanduser()
        models = Path(settings.get("model_dir", DEFAULT_MODELS)).expanduser()
        python = Path(settings.get("python_path", engine / ".venv" / "bin" / "python")).expanduser()
        if not python.is_file() or not (engine / "scripts" / "generate_staged.py").is_file():
            raise InvalidJob("Install the pinned H3 engine and its Python environment first. See the H3 plugin README.")
        if not weights_ready(models):
            raise InvalidJob("H3 weights are incomplete. Complete the H3 plugin weight setup before generating.")
        seed = job.seed if job.seed is not None else secrets.randbelow(2**32)
        request = json.dumps(
            {"prompt": job.prompt, "width": job.width, "height": job.height, "frames": job.num_frames, "seed": seed}
        ).encode()
        output = bytearray()
        buffered = ""

        def receive(chunk):
            if len(output) + len(chunk) > MAX_RESULT_BYTES:
                raise InvalidJob("H3 returned a clip larger than its output limit.")
            output.extend(chunk)

        def consume(text):
            nonlocal buffered
            buffered += text
            if len(buffered) > 16384:
                raise InvalidJob("H3 returned an invalid progress stream.")
            while "\n" in buffered:
                line, buffered = buffered.split("\n", 1)
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if (
                    isinstance(event, dict)
                    and event.get("event") == "step"
                    and type(event.get("step")) is int
                    and type(event.get("total")) is int
                    and 0 < event["step"] <= event["total"] == 8
                    and progress
                ):
                    progress(event["step"], event["total"], seed)

        self._context.run_process(
            [str(python), str(Path(__file__).with_name("worker.py")), str(engine), str(models)],
            cancelled=cancelled,
            consume=consume,
            input_bytes=request,
            consume_output=receive,
            terminate_group=True,
            timeout_seconds=7200,
            environment={"HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"},
            failure_message=lambda code, lines: f"H3 generation failed ({code}). No clip was saved.",
        )
        if len(output) < 12 or output[4:8] != b"ftyp":
            raise InvalidJob("H3 did not return an MP4 clip.")
        return VideoResult(bytes(output), job.width, job.height, job.num_frames, job.frame_rate, seed)

    def release(self):
        # The owned child exits before run returns, including cancellation and failure.
        pass
