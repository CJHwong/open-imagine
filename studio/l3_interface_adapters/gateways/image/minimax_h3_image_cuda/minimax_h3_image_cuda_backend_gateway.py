import base64

from studio.l1_entities.errors import InvalidJob, ModelOutOfDate
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.capabilities import (
    MATCH,
    minimax_h3_image_cuda_capabilities,
)
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

MAX_MATCH_PIXELS = 2048 * 2048
MAX_REFERENCE_RATIO = 4
PACK_NOT_READY = "the H3 pack is missing or out of date for this torch build"
"""What the child says when a run finds no usable pack. The child is a script of its own,
so the words are the contract between the two."""


def validate_reference_aspect(width: int, height: int) -> None:
    if max(width, height) > MAX_REFERENCE_RATIO * min(width, height):
        raise InvalidJob("Each reference must have an aspect ratio of 4:1 or less.")


def match_size(width: int, height: int) -> tuple[int, int]:
    """Keep the first reference's output size within the model's supported limits.

    The size is not rounded to the 32-pixel grid the explicit canvases use. The CUDA
    pipeline pads to its own grid internally and returns the size it was asked for:
    a 1001 by 701 reference produced a 1001 by 701 picture on 2026-11-17. Rounding here
    would quietly change the output size of every reference that is not on the grid.
    """
    if not (256 <= width <= 4096 and 256 <= height <= 4096):
        raise InvalidJob("Match requires a first reference with each side between 256 and 4096 pixels.")
    if width * height > MAX_MATCH_PIXELS:
        raise InvalidJob("Match requires a first reference with at most 4,194,304 pixels. Choose a size.")
    validate_reference_aspect(width, height)
    return width, height


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
        prepare_child: StdioChild | None = None,
        backend_id: str = "minimax_h3_image_cuda",
        name: str = "MiniMax H3-Image (CUDA)",
        badge: str = "fp8",
    ):
        self._child = child
        self._prepare_child = prepare_child
        self._backend_id = backend_id
        self._name = name
        self._badge = badge

    def capabilities(self):
        return minimax_h3_image_cuda_capabilities(self._backend_id, self._name, self._badge)

    def load(self):
        try:
            self._child.wait_ready()
        except RuntimeError as error:
            if PACK_NOT_READY not in str(error):
                raise
            raise ModelOutOfDate(
                f"{self._name}: {PACK_NOT_READY}. Prepare the model again: press Download, or run "
                "`uv run studio --prepare`."
            ) from error

    def prepare(self):
        """Start the child that may build the pack, wait for it to load, and stop it. The
        next run's child then finds the pack."""
        if self._prepare_child is None:
            self.load()
            return
        self._child.stop()
        try:
            self._prepare_child.wait_ready()
        finally:
            self._prepare_child.stop()

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
