"""Admission policy: compare an injected estimate with current memory headroom."""

from collections.abc import Callable, Mapping

from studio.l1_entities.errors import InsufficientMemory, ResourceEstimateUnavailable
from studio.l2_use_cases.boundaries.memory_estimate_gateway import MemoryEstimateGateway
from studio.l2_use_cases.boundaries.studio_settings_gateway import StudioSettingsGateway

GIB = 1024**3
OS_RESERVE_GIB = 8.0


class ResourceAdmission:
    def __init__(
        self,
        memory_headroom: Callable[[], tuple[int, int]],
        estimates: MemoryEstimateGateway,
        settings: StudioSettingsGateway,
    ):
        self._memory_headroom = memory_headroom
        self._estimates = estimates
        self._settings = settings

    def __call__(self, payload: Mapping[str, object]) -> None:
        self.check(payload)

    def check(self, payload: Mapping[str, object]) -> None:
        total_bytes, available_bytes = self._memory_headroom()
        estimate_gib = self._estimates.estimate(payload, total_bytes / GIB)
        required = self._settings.require_memory_estimate()
        items = payload.get("items")
        if required and isinstance(items, list):
            shared = {key: value for key, value in payload.items() if key != "items"}
            if any(self._estimates.estimate({**shared, **item}, total_bytes / GIB) is None for item in items):
                estimate_gib = None
        if estimate_gib is None:
            if required:
                raise ResourceEstimateUnavailable(
                    "Memory use has not been measured for this model and setup, so Studio cannot check whether it fits. "
                    "To run it anyway, open Settings > Memory and turn off 'Require a measured memory estimate', "
                    "then retry. This applies to all workspaces and API callers; known memory limits still apply."
                )
            return
        available_gib = available_bytes / GIB
        required_gib = estimate_gib + OS_RESERVE_GIB
        if required_gib > available_gib:
            raise InsufficientMemory(
                f"Not enough memory to start this request. It needs about {estimate_gib:.1f} GiB "
                f"plus {OS_RESERVE_GIB:.0f} GiB reserved for macOS; about {available_gib:.1f} GiB is available. "
                "Close other memory-heavy apps or release the loaded model, then retry. "
                "For images or video, try a smaller output or fewer references."
            )
