"""A provider-owned download or optional runtime, independent of its filesystem driver."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelAsset:
    label: str
    location: str
    kind: str = "weights"
    source: str = "directory"
    # For a pack: the fields its `pack.json` must hold for the engine to load it. It is read
    # when asked, because one field follows the hub cache, which a prepare changes.
    expected: Callable[[], Mapping] | None = field(default=None, compare=False, hash=False)
