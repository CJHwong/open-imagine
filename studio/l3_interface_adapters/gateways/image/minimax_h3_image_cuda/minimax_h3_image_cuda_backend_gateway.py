import base64
import math

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.capabilities import (
    MATCH,
    minimax_h3_image_cuda_capabilities,
)
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

# The engine takes sides that are multiples of 32, and its reference path holds an edit at
# about 4 MP: below that the result came out posterized on the MLX engine's own run.
GRID = 32
MATCH_PIXELS = 2048 * 2048


def match_size(width: int, height: int) -> tuple[int, int]:
    """The first reference's aspect at 4 MP, on the engine's grid.

    Match follows the picture, not its pixel count: an edit at 4 MP or more is the clean
    case, and a smaller frame is where this model degrades.
    """
    ratio = width / height
    wide = math.sqrt(MATCH_PIXELS * ratio)
    return (
        max(GRID, round(wide / GRID) * GRID),
        max(GRID, round(wide / ratio / GRID) * GRID),
    )


def generate_payload(job: ImageJob) -> dict:
    """One job as the child's JSON. Text and pixels cross as values, never as paths."""
    options = job.options
    width, height = (int(side) for side in str(options["size"]).split("x"))
    return {
        "mode": "generate",
        "prompt": job.prompt,
        "width": width,
        "height": height,
        "steps": int(options.get("steps", 6)),
        "seed": job.seed,
    }


def edit_payload(job: ImageJob) -> dict:
    """One edit as the child's JSON. Each reference crosses as a base64 PNG.

    The engine reads the references in order and the prompt names them `<Picture 1>`,
    `<Picture 2>`, which is the same contract the MLX backend has.
    """
    options = job.options
    first = job.references[0]
    resolution = str(options.get("size", MATCH))
    width, height = (
        (int(side) for side in resolution.split("x")) if resolution != MATCH else match_size(first.width, first.height)
    )
    return {
        "mode": "edit",
        "prompt": job.prompt,
        "width": width,
        "height": height,
        "steps": int(options.get("steps", 6)),
        "seed": job.seed,
        "references": [base64.b64encode(reference.png).decode("ascii") for reference in job.references],
    }


class MinimaxH3ImageCudaBackendGateway(ImageBackendGateway):
    """The CUDA child, kept warm between jobs: loading this checkpoint takes minutes."""

    def __init__(
        self,
        child: StdioChild,
        *,
        backend_id: str = "minimax_h3_image_cuda",
        name: str = "MiniMax H3-Image (CUDA)",
        badge: str = "fp8",
    ):
        self._child = child
        self._backend_id = backend_id
        self._name = name
        self._badge = badge

    def capabilities(self):
        return minimax_h3_image_cuda_capabilities(self._backend_id, self._name, self._badge)

    def load(self):
        self._child.wait_ready()

    def run(self, job: ImageJob, on_step, should_stop):
        payload = edit_payload(job) if job.mode == "edit" else generate_payload(job)
        reply = self._child.request(payload, on_step, should_stop)
        return ImageResult(
            png=base64.b64decode(reply["png_base64"]),
            width=int(reply["width"]),
            height=int(reply["height"]),
            seed=job.seed,
            steps=int(reply["steps"]),
        )

    def release(self):
        self._child.stop()
