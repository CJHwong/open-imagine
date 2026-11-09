"""Request-memory estimates, independent of model implementations and host probes."""

from abc import ABC, abstractmethod
from collections.abc import Mapping


class MemoryEstimateGateway(ABC):
    @abstractmethod
    def estimate(self, payload: Mapping[str, object], total_memory_gib: float) -> float | None:
        """Return the measured GiB requirement, or None for an unmeasured setup."""
