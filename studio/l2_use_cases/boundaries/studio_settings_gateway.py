"""App-wide memory policy, shared by the page and every API caller."""

from abc import ABC, abstractmethod


class StudioSettingsGateway(ABC):
    @abstractmethod
    def require_memory_estimate(self) -> bool: ...

    @abstractmethod
    def set_require_memory_estimate(self, required: bool) -> None: ...
