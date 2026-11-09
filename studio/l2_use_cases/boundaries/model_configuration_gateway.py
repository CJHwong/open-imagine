"""Resolved model settings, independent of the host configuration format."""

from typing import Any, Protocol


class ModelConfigurationGateway(Protocol):
    def backend(self, backend_id: str) -> dict[str, Any]: ...
    def required(self, backend_id: str, key: str) -> Any: ...
