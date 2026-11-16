"""LTX-2.5 on CUDA: one resident child, one clip per request."""

import base64
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.capabilities import ltx25_cuda_capabilities


def clip_payload(job: VideoJob) -> dict:
    """One job as the child's JSON. The prompt and the sizes cross as values."""
    if job.edit is not None:
        raise InvalidJob("LTX-2.5 on CUDA does not support Edit.")
    if job.audio is not None:
        raise InvalidJob("LTX-2.5 on CUDA takes no audio track.")
    if job.fast_mode:
        raise InvalidJob("LTX-2.5 on CUDA does not support Fast mode.")
    if job.loras:
        raise InvalidJob("LTX-2.5 on CUDA does not support LoRAs.")
    payload = {
        "prompt": job.prompt,
        "width": job.width,
        "height": job.height,
        "frames": job.num_frames,
        "frame_rate": job.frame_rate,
        "seed": job.seed if job.seed is not None else 0,
        "enhance": bool(job.enhance),
        "include_audio": job.include_audio,
    }
    if job.references:
        payload["references"] = [
            {
                "png_base64": base64.b64encode(reference.png).decode("ascii"),
                "frame_index": reference.frame_index,
                "strength": reference.strength,
            }
            for reference in job.references
        ]
    return payload


class Ltx25CudaBackendGateway(VideoBackendGateway):
    def __init__(self, child: StdioChild):
        self._child = child

    def capabilities(self) -> VideoCapabilities:
        return ltx25_cuda_capabilities()

    def load(self) -> None:
        self._child.wait_ready()

    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VideoResult:
        if cancelled is not None and cancelled():
            raise Cancelled("Video generation was cancelled.")

        def on_step(step: int, total: int) -> None:
            if progress is not None:
                progress(1, step, total)

        reply = self._child.request(clip_payload(job), on_step, cancelled or (lambda: False))
        return VideoResult(
            mp4=base64.b64decode(reply["mp4"]),
            width=int(reply["width"]),
            height=int(reply["height"]),
            num_frames=int(reply["frames"]),
            frame_rate=job.frame_rate,
            seed=job.seed,
        )

    def release(self) -> None:
        self._child.stop()
