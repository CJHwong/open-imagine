"""Selectable model providers, independent of discovery and SDK registration formats."""

from typing import Protocol

from studio.l2_use_cases.model_provider import ModelProvider


class ModelCatalogGateway(Protocol):
    def ids(self, kind: str) -> tuple[str, ...]: ...
    def provider(self, kind: str, name: str) -> ModelProvider: ...
