"""Metadata and lazy declarations needed by model construction."""

from typing import Protocol

from studio.plugins.registration import ModelRegistration


class ModelRegistrationCatalog(Protocol):
    def ids(self, kind: str) -> tuple[str, ...]: ...
    def declaration(self, kind: str, name: str) -> ModelRegistration: ...
