"""What a video run would do, without running it.

The video side of `plan_image_use_case.py`: the run's own checks, the settings that the clip
would take, and the time. It reads the named model's capabilities only, so it loads no
weights, takes no lock and leaves the active model as it is.
"""

from dataclasses import dataclass

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.lora import LoraUse
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_estimate import ClipEstimate, estimate_clip
from studio.l2_use_cases.boundaries.video_backend_catalog_gateway import VideoBackendCatalogGateway


@dataclass(frozen=True)
class PlanVideoRequest:
    """One clip, checked as a run checks it. The media do not travel: `references` counts the
    images, and `audio` says whether a track drives the clip."""

    backend: str
    mode: str
    width: int
    height: int
    num_frames: int
    frame_rate: int
    references: int = 0
    audio: bool = False
    enhance: bool = True
    fast_mode: bool = False
    loras: tuple[LoraUse, ...] = ()
    adapter: str = ""  # the effect of an edit
    adapter_strength: float | None = None


@dataclass(frozen=True)
class PlanVideoResponse:
    backend: str
    mode: str
    count: int
    effective_options: dict[str, object]
    """The clip's settings, as the run would take them."""
    loras: tuple[LoraUse, ...]
    offers_loras: bool
    estimate: ClipEstimate


class PlanVideoUseCase:
    def __init__(self, catalog: VideoBackendCatalogGateway):
        self._catalog = catalog

    def capabilities(self, backend_id: str) -> tuple[str, VideoCapabilities]:
        """The model that a plan reads, and its capabilities: the one it names, or the active one."""
        backend_id = backend_id or self._catalog.active_id()
        if backend_id not in self._catalog.visible_ids():
            raise InvalidJob(f"No video model is offered as {backend_id}.")
        return backend_id, self._catalog.get(backend_id).capabilities()

    def execute(self, request: PlanVideoRequest) -> PlanVideoResponse:
        backend_id, capabilities = self.capabilities(request.backend)
        adapter = next((one for one in capabilities.adapters if one.id == request.adapter), None)
        estimate = estimate_clip(
            capabilities.estimate,
            request.width,
            request.height,
            request.num_frames,
            references=request.references,
            loras=len(request.loras),
            audio=request.audio,
            enhance=request.enhance,
            fast_mode=request.fast_mode,
            adapter=adapter,
        )
        options: dict[str, object] = {
            "width": request.width,
            "height": request.height,
            "num_frames": request.num_frames,
            "frame_rate": request.frame_rate,
            "enhance": request.enhance,
            "fast_mode": request.fast_mode,
        }
        if adapter is not None:
            options.update(adapter=adapter.id, adapter_strength=request.adapter_strength)
        return PlanVideoResponse(
            backend_id, request.mode, 1, options, request.loras, bool(capabilities.loras), estimate
        )
