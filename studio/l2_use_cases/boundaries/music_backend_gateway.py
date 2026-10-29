from abc import ABC, abstractmethod
from collections.abc import Callable

from studio.l1_entities.music_capabilities import MusicCapabilities
from studio.l1_entities.music_job import MusicJob, MusicResult


class MusicBackendGateway(ABC):
    @abstractmethod
    def capabilities(self) -> MusicCapabilities:
        """Static model controls; loads nothing."""

    @abstractmethod
    def load(self) -> None:
        """Prepare the engine idempotently."""

    @abstractmethod
    def run(self, job: MusicJob, on_step: Callable[[int, int], None], should_stop: Callable[[], bool]) -> MusicResult:
        """Return one stereo recording; observe cancellation during every stage."""

    @abstractmethod
    def release(self) -> None:
        """Release all owned model memory; tolerate repeated calls."""
