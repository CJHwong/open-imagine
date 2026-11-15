import base64
import math

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.image.qwen21_cuda.capabilities import qwen21_cuda_capabilities
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_controls import MATCH
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_sizes import EDIT_MATCH_CAP
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

# The model works on a 32-pixel grid, the same one the MLX edit path holds to.
GRID = 32


def on_the_grid(side: float) -> int:
    """The largest size on the model's 32-pixel grid that `side` allows.

    Floor rather than nearest: a match may come out slightly smaller than the
    reference, and never larger than the frame the cap allowed.
    """
    return max(GRID, GRID * int(side // GRID))


def match_resolution(width: int, height: int) -> int:
    """The side of the square area an edit aims at, held to the cap the MLX path uses.

    The pipeline sizes the output from the last condition image's aspect at this area,
    on its own 32-pixel grid. An edit pays for every pixel it renders, so a screenshot
    at 2560x1440 must not ask for the frame it came in at.
    """
    return min(EDIT_MATCH_CAP, on_the_grid(math.sqrt(width * height)))


def generate_payload(job: ImageJob) -> dict:
    """One job as the child's JSON. Text and pixels cross as values, never as paths."""
    options = job.options
    width, height = (int(side) for side in str(options["size"]).split("x"))
    return {
        "mode": "generate",
        "prompt": job.prompt,
        "negative": options.get("negative") or "",
        "width": width,
        "height": height,
        "steps": int(options.get("steps", 8)),
        "guidance": float(options.get("guidance", 1.0)),
        "seed": job.seed,
    }


def edit_payload(job: ImageJob) -> dict:
    """One edit as the child's JSON. Each reference crosses as a base64 PNG, never a path.

    `resolution` is "match" or a side in pixels. Match follows the last reference, which
    is what the pipeline sizes its output from.
    """
    options = job.options
    last = job.references[-1]
    resolution = str(options.get("resolution", MATCH))
    output_resolution = match_resolution(last.width, last.height) if resolution == MATCH else int(resolution)
    return {
        "mode": "edit",
        "prompt": job.prompt,
        "negative": options.get("negative") or "",
        "output_resolution": output_resolution,
        "steps": int(options.get("steps", 8)),
        "guidance": float(options.get("guidance", 1.0)),
        "seed": job.seed,
        "references": [base64.b64encode(reference.png).decode("ascii") for reference in job.references],
    }


class Qwen21CudaBackendGateway(ImageBackendGateway):
    """The CUDA child, kept warm between jobs: loading these weights takes seconds, not minutes."""

    def __init__(self, child: StdioChild, *, badge: str):
        self._child = child
        self._badge = badge

    def capabilities(self):
        return qwen21_cuda_capabilities(self._badge)

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
