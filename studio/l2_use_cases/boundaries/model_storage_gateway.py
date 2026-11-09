"""Inspect and remove only assets declared by model providers."""

from typing import Protocol


class ModelStorageGateway(Protocol):
    def inventory(self) -> dict: ...
    def remove(self, asset_ids: tuple[str, ...], revision: str) -> dict: ...
