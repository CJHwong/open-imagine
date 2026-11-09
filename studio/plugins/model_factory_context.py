"""Dependencies supplied to a model backend factory."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelFactoryContext:
    """Resolved model settings and the host's cancellable subprocess driver."""

    settings: Mapping[str, Any]
    run_process: Callable[..., Any]
