"""Select injected estimators and account for retained batch results."""

import sys
from collections.abc import Callable, Mapping

from studio.l2_use_cases.boundaries.memory_estimate_gateway import MemoryEstimateGateway


class CatalogMemoryEstimateGateway(MemoryEstimateGateway):
    def __init__(
        self,
        estimators: Mapping[tuple[str, str], Callable[[Mapping[str, object]], float | None]],
        *,
        platform: str = "darwin",
        total_memory_gib: float = 64.0,
    ):
        self._estimators = dict(estimators)
        self._platform = platform
        self._total_memory_gib = total_memory_gib

    def estimate(self, payload: Mapping[str, object], total_memory_gib: float) -> float | None:
        if sys.platform != self._platform or total_memory_gib != self._total_memory_gib:
            return None
        items = payload.get("items")
        if not isinstance(items, list):
            return self._estimate_one(payload)
        estimates = []
        shared = {key: value for key, value in payload.items() if key != "items"}
        for item in items:
            if not isinstance(item, Mapping):
                return None
            estimate = self._estimate_one({**shared, **item})
            if estimate is not None:
                estimates.append(estimate)
        if not estimates:
            return None
        # An unmeasured item must not hide a measured item's memory requirement.
        # Batches retain finished media while the next item runs, including unmeasured items.
        return max(estimates) + max(0, len(items) - 1) * 0.125

    def _estimate_one(self, payload: Mapping[str, object]) -> float | None:
        estimator = self._estimators.get((str(payload.get("kind")), str(payload.get("backend"))))
        return estimator(payload) if estimator is not None else None
