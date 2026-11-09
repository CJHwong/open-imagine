"""One model's construction and optional measured services; no engine is loaded here."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from studio.l1_entities.model_asset import ModelAsset
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway


@dataclass(frozen=True)
class ModelProvider:
    backend_id: str
    kind: str
    create: Callable[..., Any]
    estimator: Callable[..., Any] | None = None
    rewriter: Callable[..., Any] | None = None
    rewriter_cache: Callable[..., str] | None = None
    requires_mlx: bool = True
    storage_assets: Callable[[ModelConfigurationGateway], tuple[ModelAsset, ...]] | None = None
    storage_name: str = ""
    storage_roots: tuple[str, ...] = ()
