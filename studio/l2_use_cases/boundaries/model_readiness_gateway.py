from abc import ABC, abstractmethod

from studio.l1_entities.model_readiness import ModelReadiness


class ModelReadinessGateway(ABC):
    """What a model needs on disk before it runs, and the record of a prepare that proved it.

    A model is ready when a prepare loaded its whole selection, the engine and its prompt
    rewriter, and the files that prepare read are still there. The record is what makes
    the answer honest: only a load proves that every file an engine fetches is present,
    because an engine can fetch more than its declared repository.
    """

    @abstractmethod
    def readiness(self, backend_id: str) -> ModelReadiness:
        """This model's state from its files and its record. Loads nothing."""

    @abstractmethod
    def mark_prepared(self, backend_id: str) -> None:
        """Record that a prepare loaded this model's selection under its current settings."""
