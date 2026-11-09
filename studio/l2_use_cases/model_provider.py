"""One model's construction and optional measured services; no engine is loaded here."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelProvider:
    backend_id: str
    kind: str
    create: Callable[..., Any]
    estimator: Callable[..., Any] | None = None
    rewriter: Callable[..., Any] | None = None
    rewriter_cache: Callable[..., str] | None = None
    requires_mlx: bool = True
