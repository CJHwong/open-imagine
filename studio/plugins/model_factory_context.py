"""Dependencies supplied to a model backend factory."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from studio.l1_entities.video_capabilities import VideoCapabilities


@dataclass(frozen=True)
class ModelFactoryContext:
    """Resolved model settings and the host's cancellable subprocess driver."""

    settings: Mapping[str, Any]
    run_process: Callable[..., Any]

    capabilities: VideoCapabilities | None = None
    lora_paths: Mapping[str, str] = field(default_factory=dict)
