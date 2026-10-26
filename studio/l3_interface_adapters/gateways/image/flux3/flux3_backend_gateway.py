"""Run the pinned newer MLX engine in one owned child, without upgrading Qwen."""

import io
import json
import math
import os
import tempfile
from pathlib import Path

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.image.flux3.capabilities import flux3_capabilities


def image_size(job: ImageJob) -> tuple[int, int]:
    if job.options["size"] != "match":
        width, height = (int(side) for side in str(job.options["size"]).split("x"))
        return width, height
    if not job.references:
        return 1024, 1024
    first = job.references[0]
    scale = min(1.0, math.sqrt(1024 * 1024 / (first.width * first.height)), 2048 / max(first.width, first.height))
    width, height = (int(side * scale) // 16 * 16 for side in (first.width, first.height))
    if min(width, height) < 64:
        raise InvalidJob("Match needs at least 64 pixels per side after fitting. Choose a supported size.")
    return width, height


def engine_failure(code, lines):
    recent = list(lines)
    detail = recent[-1] if recent else "no error output"
    return f"FLUX3 engine exited {code}: {detail}"


class Flux3BackendGateway(ImageBackendGateway):
    def __init__(self, model_dir: str, python_path: str, quantize: int | None, badge: str, execute_process):
        self._model_dir = model_dir
        self._python_path = python_path
        self._quantize = quantize
        self._badge = badge
        self._execute = execute_process

    def capabilities(self):
        return flux3_capabilities(self._badge)

    def load(self):
        # Readiness only: the child loads weights inside run, not at startup or selection.
        if not Path(self._python_path).is_file():
            raise InvalidJob("FLUX3 runtime is missing. Follow the FLUX3 setup in docs/how-to/set-up-models.md.")
        if not Path(self._model_dir).is_dir():
            raise InvalidJob("FLUX3 weights are missing. Follow the FLUX3 setup in docs/how-to/set-up-models.md.")
        if self._quantize not in (None, 4, 6, 8):
            raise InvalidJob("FLUX3 quantize must be 0, 4, 6 or 8.")

    def release(self):
        # No resident worker: execute waits for this direct Python child to exit.
        pass

    def run(self, job, on_step, should_stop):
        from PIL import Image

        if should_stop():
            raise Cancelled("FLUX3 stopped")
        self.load()
        width, height = image_size(job)
        steps = int(job.options["steps"])
        on_step(0, steps)
        pending = ""

        def consume(chunk):
            nonlocal pending
            pending += chunk
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                if line.startswith("FLUX3_EVENT "):
                    event = json.loads(line.removeprefix("FLUX3_EVENT "))
                    if event["type"] == "step":
                        on_step(event["step"], event["total"])
            pending = pending[-16384:]

        with tempfile.TemporaryDirectory(prefix="studio-flux3-") as directory:
            root = Path(directory)
            references = []
            for index, reference in enumerate(job.references):
                path = root / f"reference-{index}.png"
                path.write_bytes(reference.png)
                references.append(str(path))
            output = root / "result.png"
            request = root / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "mode": job.mode,
                        "prompt": job.prompt,
                        "seed": job.seed,
                        "width": width,
                        "height": height,
                        "steps": steps,
                        "references": references,
                        "quantize": self._quantize,
                        "model_dir": self._model_dir,
                    }
                )
            )
            self._execute(
                [self._python_path, str(Path(__file__).with_name("flux3_child.py")), str(request), str(output)],
                cancelled=should_stop,
                consume=consume,
                environment={"PATH": "/opt/homebrew/bin:" + os.environ.get("PATH", ""), "HF_HUB_OFFLINE": "1"},
                timeout_seconds=1500,
                failure_message=engine_failure,
            )
            if should_stop():
                raise Cancelled("FLUX3 stopped")
            if not output.is_file():
                raise InvalidJob("FLUX3 engine returned no image.")
            png = output.read_bytes()
            with Image.open(io.BytesIO(png)) as image:
                image.load()
                if image.format != "PNG" or image.size != (width, height):
                    raise InvalidJob("FLUX3 engine returned an unexpected image format or size.")
            return ImageResult(png, width, height, job.seed, steps)
