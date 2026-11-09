"""A provider-owned download or optional runtime, independent of its filesystem driver."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelAsset:
    label: str
    location: str
    kind: str = "weights"
    source: str = "directory"
