from abc import ABC, abstractmethod


class ModelResidencyGateway(ABC):
    """Own the studio's model memory under one of two release policies.

    `immediate` keeps one model: a claim or a selection frees the other, as the studio
    always did. `boundary` keeps every model whose measured footprint fits, oldest first,
    and frees the oldest only when another model would take the total past the boundary.
    Both policies allow one claim at a time, because one GPU serves them.
    """

    @abstractmethod
    def select(self, backend_id: str) -> None:
        """Record the model that the next run will use. Load nothing; free the old model
        only when the policy is immediate."""

    @abstractmethod
    def claim(self, backend_id: str) -> tuple[str, ...]:
        """Make room for this model before its run, and name the models that it freed."""

    @abstractmethod
    def release_active(self) -> None:
        """Free the model that the last claim named, and leave no model active."""

    @abstractmethod
    def release_idle(self) -> None:
        """Free the loaded models when the policy is immediate; keep them under boundary."""

    @abstractmethod
    def release(self) -> None:
        """Free every model now, whatever the policy."""
