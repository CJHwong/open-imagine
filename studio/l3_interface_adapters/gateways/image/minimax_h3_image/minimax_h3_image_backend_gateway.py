"""Run the pinned h3-image-mlx engine, one owned child per stage, from its own script environment."""

import io
import json
import math
import os
import shutil
import tempfile
from pathlib import Path

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.capabilities import (
    EDIT_PIXELS,
    GRID,
    STEP_COUNT,
    minimax_h3_image_capabilities,
)

SETUP = "Follow the MiniMax H3-Image setup in docs/how-to/set-up-models.md."
WEIGHT_FILES = (
    "diffusion_models/minimax_h3_image_pruned_int8_convrot.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
    "vae/minimax_h3_image_vae_fp16.safetensors",
    "vae/config.json",
    "tokenizer.json",
)
# The engine reads a reference with its short side held between 1024 and 2048 pixels, so a
# long reference costs more pixels than a square one. The measured runs took references of
# 2048 x 2048 at most. A reference of 4:1 at most, sent at that pixel count at most, stays
# inside them: the engine then reads 4096 x 1024 or less. Refuse a longer one before a 27 GB
# encoder loads.
MAX_REFERENCE_RATIO = 4.0
MAX_REFERENCE_PIXELS = 2048 * 2048
# Match keeps the reference's shape at about 4 MP. Past 4:1 the long side passes the engine's
# 4096 pixels, and a smaller output falls under the area an edit needs.
MAX_MATCH_RATIO = 4.0
EVENT = "H3_IMAGE_EVENT "


def image_size(job: ImageJob) -> tuple[int, int]:
    if job.options["size"] != "match":
        width, height = (int(side) for side in str(job.options["size"]).split("x"))
        return width, height
    first = job.references[0]
    if max(first.width, first.height) > MAX_MATCH_RATIO * min(first.width, first.height):
        raise InvalidJob("Match takes a first reference of 4:1 at most. Choose a size.")
    scale = math.sqrt(EDIT_PIXELS / (first.width * first.height))
    width, height = (min(4096, max(GRID, round(side * scale / GRID) * GRID)) for side in (first.width, first.height))
    return width, height


def reference_png(reference) -> bytes:
    """The reference for the engine in RGB, made smaller when it has more pixels than a measured one.

    Every reference is decoded and written again, so the engine reads one pixel format at
    every size: a palette or alpha input reaches it as RGB."""
    from PIL import Image

    pixels = reference.width * reference.height
    data = io.BytesIO()
    with Image.open(io.BytesIO(reference.png)) as image:
        converted = image.convert("RGB")
        if pixels > MAX_REFERENCE_PIXELS:
            scale = math.sqrt(MAX_REFERENCE_PIXELS / pixels)
            size = (max(1, int(reference.width * scale)), max(1, int(reference.height * scale)))
            converted = converted.resize(size, Image.Resampling.LANCZOS)
        converted.save(data, format="PNG")
    return data.getvalue()


def engine_failure(code, lines):
    recent = list(lines)
    detail = recent[-1] if recent else "no error output"
    return f"MiniMax H3-Image engine exited {code}: {detail}"


def uv_launcher() -> str:
    """The uv that runs the studio, so a child's script environment uses the same version.

    The parent uv exports its own path as UV. A server started another way falls back to PATH.
    """
    launcher = os.environ.get("UV") or shutil.which("uv")
    if not launcher:
        raise InvalidJob(
            "MiniMax H3-Image needs uv on PATH. Install uv, or add it to PATH, and start the server with it. " + SETUP
        )
    return launcher


class MinimaxH3ImageBackendGateway(ImageBackendGateway):
    def __init__(self, model_dir: str, execute_process):
        self._model_dir = model_dir
        self._execute = execute_process

    def capabilities(self):
        return minimax_h3_image_capabilities()

    def load(self):
        # Readiness only: each stage child loads its own weights inside run.
        if not all((Path(self._model_dir) / name).is_file() for name in WEIGHT_FILES):
            raise InvalidJob(f"MiniMax H3-Image weights are missing. {SETUP}")

    def release(self):
        # No resident worker: execute waits for each stage child to exit, and the exit frees its weights.
        pass

    def run(self, job, on_step, should_stop):
        from PIL import Image

        if should_stop():
            raise Cancelled("MiniMax H3-Image stopped")
        launcher = uv_launcher()
        self.load()
        for reference in job.references:
            if max(reference.width, reference.height) > MAX_REFERENCE_RATIO * min(reference.width, reference.height):
                raise InvalidJob("A reference is too narrow for MiniMax H3-Image. Crop it to 4:1 at most.")
        width, height = image_size(job)
        on_step(0, STEP_COUNT)
        pending = ""

        def consume(chunk):
            nonlocal pending
            pending += chunk
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                if line.startswith(EVENT):
                    # Progress only: a line that does not parse must not end a run that still works.
                    try:
                        event = json.loads(line.removeprefix(EVENT))
                        step = event["step"] if event["type"] == "step" else None
                    except (ValueError, KeyError, TypeError):
                        continue
                    if step is not None:
                        on_step(step, STEP_COUNT)
            pending = pending[-16384:]

        with tempfile.TemporaryDirectory(prefix="studio-h3-image-") as directory:
            root = Path(directory)
            references = []
            for index, reference in enumerate(job.references):
                path = root / f"reference-{index}.png"
                path.write_bytes(reference_png(reference))
                references.append(str(path))
            # The engine's own request format. "auto" lets it pick the kernel and the resident
            # transformer from the machine, as its command line does.
            (root / "request.json").write_text(
                json.dumps(
                    {
                        "prompt": job.prompt,
                        "models": self._model_dir,
                        "width": width,
                        "height": height,
                        "seed": job.seed,
                        "references": references,
                        "backend": "auto",
                        "dit_mode": "auto",
                    }
                )
            )
            child = str(Path(__file__).with_name("minimax_h3_image_child.py"))
            for stage in ("text", *(("references",) if references else ()), "dit", "vae"):
                self._execute(
                    [launcher, "run", "--script", child, stage, str(root)],
                    cancelled=should_stop,
                    consume=consume,
                    # The engine launches its own stages with the script environment's Python,
                    # so no external binary comes from PATH. The launcher is absolute.
                    environment={"HF_HUB_OFFLINE": "1"},
                    timeout_seconds=1500,
                    failure_message=engine_failure,
                )
                if should_stop():
                    raise Cancelled("MiniMax H3-Image stopped")
            output = root / "image.png"
            if not output.is_file():
                raise InvalidJob("MiniMax H3-Image engine returned no image.")
            png = output.read_bytes()
            with Image.open(io.BytesIO(png)) as image:
                image.load()
                if image.format != "PNG" or image.size != (width, height):
                    raise InvalidJob("MiniMax H3-Image engine returned an unexpected image format or size.")
            return ImageResult(png, width, height, job.seed, STEP_COUNT)
