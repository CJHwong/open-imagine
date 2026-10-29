from abc import ABC, abstractmethod

from studio.l2_use_cases.boundaries.music_backend_gateway import MusicBackendGateway


class MusicBackendCatalogGateway(ABC):
    """Registered music models, the models the page may offer, and the selected one."""

    @abstractmethod
    def get(self, backend_id: str) -> MusicBackendGateway:
        """Return a registered music model or raise UnknownBackend."""

    @abstractmethod
    def visible_ids(self) -> tuple[str, ...]:
        """Return models in page display order."""

    @abstractmethod
    def active_id(self) -> str:
        """Return the selected music model."""

    @abstractmethod
    def set_active(self, backend_id: str) -> None:
        """Select a registered music model."""
