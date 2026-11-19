from abc import ABC, abstractmethod


class ModelLifecycleGateway(ABC):
    """The two operations the studio needs to hold a model and give it back."""

    @abstractmethod
    def load(self) -> None:
        """Make this model ready to run. Calling it again does nothing."""

    @abstractmethod
    def release(self) -> None:
        """Free this model's memory, if it is resident."""

    def prepare(self) -> None:
        """Load as a prepare: the one load allowed to download or build what a run reads.

        Most models fetch and build in their ordinary load, so this is that load. A model
        whose run must not build overrides it.
        """
        self.load()
