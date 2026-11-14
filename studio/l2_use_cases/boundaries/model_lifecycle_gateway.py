from abc import ABC, abstractmethod


class ModelLifecycleGateway(ABC):
    """The two operations the studio needs to hold a model and give it back."""

    @abstractmethod
    def load(self) -> None:
        """Make this model ready to run. Calling it again does nothing."""

    @abstractmethod
    def release(self) -> None:
        """Free this model's memory, if it is resident."""
