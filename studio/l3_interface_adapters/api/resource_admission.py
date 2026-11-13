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
        resident_gib: Callable[[str], float] | None = None,
    ):
        self._memory_headroom = memory_headroom
        self._estimates = estimates
        self._settings = settings
        self._resident_gib = resident_gib

    def __call__(self, payload: Mapping[str, object]) -> None:
        self.check(payload)

    def check(self, payload: Mapping[str, object]) -> None:
        if not self._settings.require_memory_estimate():
            return
        total_bytes, available_bytes = self._memory_headroom()
        estimate_gib = self._estimate(payload, total_bytes)
        if estimate_gib is None:
            raise self._unavailable()
        available_gib = available_bytes / GIB
        needed_gib = self._needed(estimate_gib, payload)
        required_gib = needed_gib + OS_RESERVE_GIB
        if required_gib > available_gib:
            raise InsufficientMemory(
                f"Not enough memory to start this request. It needs about {needed_gib:.1f} GiB "
                f"plus {OS_RESERVE_GIB:.0f} GiB reserved for macOS; about {available_gib:.1f} GiB is available. "
                "Close other memory-heavy apps or release the loaded model, then retry. "
                "For images or video, try a smaller output or fewer references."
            )

    def require(self, payload: Mapping[str, object]) -> None:
        """Refuse a request whose setup has never been measured, before it is queued.

        The headroom comparison waits for the run, because free memory changes while a
        request waits. Whether a measurement exists at all does not change.
        """
        if not self._settings.require_memory_estimate():
            return
        total_bytes, _ = self._memory_headroom()
        if self._estimate(payload, total_bytes) is None:
            raise self._unavailable()

    def _needed(self, estimate_gib: float, payload: Mapping[str, object]) -> float:
        """The run's peak, less the model that is loaded already.

        Free memory leaves out a loaded model, and the measured peak counts it again,
        so charging the whole peak would ask for the model twice. The subtraction
        charges only what the run allocates on top of the weights it already holds.
        """
        if self._resident_gib is None:
            return estimate_gib
        backend = payload.get("backend")
        return max(0.0, estimate_gib - self._resident_gib(str(backend or "")))

    def _estimate(self, payload: Mapping[str, object], total_bytes: int) -> float | None:
        estimate_gib = self._estimates.estimate(payload, total_bytes / GIB)
        items = payload.get("items")
        if isinstance(items, list):
            shared = {key: value for key, value in payload.items() if key != "items"}
            if any(self._estimates.estimate({**shared, **item}, total_bytes / GIB) is None for item in items):
                estimate_gib = None
        return estimate_gib

    @staticmethod
    def _unavailable() -> ResourceEstimateUnavailable:
        return ResourceEstimateUnavailable(
            "Memory use has not been measured for this model and setup, so Studio cannot check whether it fits. "
            "To run it anyway, open Settings > Generation and turn off 'Check memory before generation', "
            "then retry. Turning this off skips all memory admission checks for all workspaces and API callers."
        )
