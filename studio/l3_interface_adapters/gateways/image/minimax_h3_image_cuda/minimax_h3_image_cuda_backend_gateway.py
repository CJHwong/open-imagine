import base64

from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.capabilities import (
    minimax_h3_image_cuda_capabilities,
)
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild


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


class MinimaxH3ImageCudaBackendGateway(ImageBackendGateway):
    """The CUDA child, kept warm between jobs: loading this checkpoint takes minutes."""

    def __init__(self, child: StdioChild, *, badge: str):
        self._child = child
        self._badge = badge

    def capabilities(self):
        return minimax_h3_image_cuda_capabilities(self._badge)

    def load(self):
        self._child.wait_ready()

    def run(self, job: ImageJob, on_step, should_stop):
        reply = self._child.request(generate_payload(job), on_step, should_stop)
        return ImageResult(
            png=base64.b64decode(reply["png_base64"]),
            width=int(reply["width"]),
            height=int(reply["height"]),
            seed=job.seed,
            steps=int(reply["steps"]),
        )

    def release(self):
        self._child.stop()
