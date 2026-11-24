"""MiniMax H3 on CUDA: one resident child, one clip per request."""

import base64
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.capabilities import (
    FAST_STEPS,
    STEPS,
    minimax_h3_cuda_capabilities,
)


def _png(reference) -> str:
    return base64.b64encode(reference.png).decode("ascii")


def clip_payload(job: VideoJob) -> dict:
    """One job as the child's JSON.

    Pictures run the reference workflow, with the track when there is one. The pipeline refuses
    a track on its own, and takes no keyframe beside the pictures. The track steers the sound
    the model generates; the clip is not timed to it. A track sent with keyframes and no
    pictures is the older form of the same run: each keyframe stands for a picture, wherever it
    was placed. Otherwise a still is a keyframe, which the pipeline takes only as the first or
    the last frame.
    """
    if job.edit is not None:
        raise InvalidJob("MiniMax H3 on CUDA does not support Edit.")
    if job.loras:
        raise InvalidJob("MiniMax H3 on CUDA does not support LoRAs.")
    payload = {
        "prompt": job.prompt,
        "width": job.width,
        "height": job.height,
        "frames": job.num_frames,
        "seed": job.seed if job.seed is not None else 0,
        "steps": FAST_STEPS if job.fast_mode else STEPS,
        "include_audio": job.include_audio,
    }
    if job.pictures and job.references:
        raise InvalidJob("MiniMax H3 on CUDA takes pictures or keyframes, not both.")
    pictures = job.pictures or (job.references if job.audio is not None else ())
    if job.audio is not None and not pictures:
        raise InvalidJob(
            "MiniMax H3 on CUDA needs a picture with an audio track. Add a picture of who or what to show."
        )
    if pictures:
        payload["pictures"] = [_png(picture) for picture in pictures]
        if job.audio is not None:
            payload["audio"] = base64.b64encode(job.audio.data).decode("ascii")
        return payload
    last = job.num_frames - 1
    frames = [reference.frame_index for reference in job.references]
    if len(set(frames)) < len(frames):
        raise InvalidJob("MiniMax H3 on CUDA takes one still per frame. Remove the second still on the same frame.")
    for reference in job.references:
        if reference.frame_index not in (0, last):
            raise InvalidJob(
                "MiniMax H3 on CUDA places a still only on the first or the last frame. "
                f"Move the still at frame {reference.frame_index} to frame 0 or {last}."
            )
    by_frame = {reference.frame_index: reference for reference in job.references}
    if 0 in by_frame:
        payload["first"] = _png(by_frame[0])
    if last in by_frame and last != 0:
        payload["last"] = _png(by_frame[last])
    return payload


class MinimaxH3CudaBackendGateway(VideoBackendGateway):
    def __init__(self, child: StdioChild):
        self._child = child

    def capabilities(self) -> VideoCapabilities:
        return minimax_h3_cuda_capabilities()

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
        payload = clip_payload(job)

        def on_step(step: int, total: int) -> None:
            if progress is not None:
                progress(step, total, 1)

        reply = self._child.request(payload, on_step, cancelled or (lambda: False))
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
