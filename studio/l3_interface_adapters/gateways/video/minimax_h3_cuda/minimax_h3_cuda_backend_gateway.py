"""MiniMax H3 on CUDA: one resident child, one clip per request. HyperFlow H3 Flash runs on the
same child and the same form, with its own transformers and schedule."""

import base64
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.capabilities import (
    CAPABILITIES,
    FAST_STEPS,
    FLASH_STEPS,
    STEPS,
)


def _png(reference) -> str:
    return base64.b64encode(reference.png).decode("ascii")


def base_schedule(fast_mode: bool) -> tuple[int, int]:
    """The steps diffusers is asked for, and the transformer calls they make: diffusers counts
    sigma points, the final 0 among them."""
    steps = FAST_STEPS if fast_mode else STEPS
    return steps, steps - 1


def flash_schedule(fast_mode: bool) -> tuple[int, int]:
    """Flash's sampler counts transformer calls, on a grid of 4, 6 or 8."""
    if fast_mode:
        raise InvalidJob("HyperFlow H3 Flash on CUDA does not support Fast mode.")
    return FLASH_STEPS, FLASH_STEPS


def clip_payload(
    job: VideoJob, name: str = CAPABILITIES.name, schedule: Callable[[bool], tuple[int, int]] = base_schedule
) -> dict:
    """One job as the child's JSON.

    Pictures run the reference workflow, with the track when there is one. The pipeline refuses
    a track on its own, and takes no keyframe beside the pictures. The track steers the sound
    the model generates; the clip is not timed to it. A track sent with keyframes and no
    pictures is the older form of the same run: each keyframe stands for a picture, wherever it
    was placed. Otherwise a still is a keyframe, which the pipeline takes only as the first or
    the last frame.
    """
    if job.edit is not None:
        raise InvalidJob(f"{name} on CUDA does not support Edit.")
    if job.loras:
        raise InvalidJob(f"{name} on CUDA does not support LoRAs.")
    steps, forwards = schedule(job.fast_mode)
    payload = {
        "prompt": job.prompt,
        "width": job.width,
        "height": job.height,
        "frames": job.num_frames,
        "seed": job.seed if job.seed is not None else 0,
        "steps": steps,
        "forwards": forwards,
        "include_audio": job.include_audio,
    }
    if job.pictures and job.references:
        raise InvalidJob(f"{name} on CUDA takes pictures or keyframes, not both.")
    pictures = job.pictures or (job.references if job.audio is not None else ())
    if job.audio is not None and not pictures:
        raise InvalidJob(f"{name} on CUDA needs a picture with an audio track. Add a picture of who or what to show.")
    if pictures:
        payload["pictures"] = [_png(picture) for picture in pictures]
        if job.audio is not None:
            payload["audio"] = base64.b64encode(job.audio.data).decode("ascii")
        return payload
    last = job.num_frames - 1
    frames = [reference.frame_index for reference in job.references]
    if len(set(frames)) < len(frames):
        raise InvalidJob(f"{name} on CUDA takes one still per frame. Remove the second still on the same frame.")
    for reference in job.references:
        if reference.frame_index not in (0, last):
            raise InvalidJob(
                f"{name} on CUDA places a still only on the first or the last frame. "
                f"Move the still at frame {reference.frame_index} to frame 0 or {last}."
            )
    by_frame = {reference.frame_index: reference for reference in job.references}
    if 0 in by_frame:
        payload["first"] = _png(by_frame[0])
    if last in by_frame and last != 0:
        payload["last"] = _png(by_frame[last])
    return payload


class MinimaxH3CudaBackendGateway(VideoBackendGateway):
    def __init__(
        self,
        child: StdioChild,
        capabilities: VideoCapabilities = CAPABILITIES,
        schedule: Callable[[bool], tuple[int, int]] = base_schedule,
    ):
        self._child = child
        self._capabilities = capabilities
        self._schedule = schedule

    def capabilities(self) -> VideoCapabilities:
        return self._capabilities

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
        payload = clip_payload(job, self._capabilities.name, self._schedule)

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
