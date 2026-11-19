from abc import ABC, abstractmethod

from studio.l1_entities.model_readiness import ModelReadiness


class ModelReadinessGateway(ABC):
    """Whether a model's files are on disk, so a run can load it without a download.

    The files decide. The one thing they cannot show is a pack that is present but out
    of date for this machine, so a run that finds one marks the model until a prepare
    succeeds.
    """

    @abstractmethod
    def readiness(self, backend_id: str) -> ModelReadiness:
        """This model's state from its files. Loads nothing."""

    @abstractmethod
    def mark_prepared(self, backend_id: str) -> None:
        """A prepare loaded this model: forget any out-of-date mark."""

    @abstractmethod
    def mark_unprepared(self, backend_id: str) -> None:
        """A run found this model's files present but unusable: it needs a prepare."""
