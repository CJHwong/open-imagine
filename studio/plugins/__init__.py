"""Version 1 public contract for separately installed Open Imagine model packages.

Factories and capabilities must be cheap: import engines and load weights only
inside gateway.load/run. Use the media modules for job, result and capability types.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from studio.l1_entities.capabilities import Capabilities as ImageCapabilities
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.voice_capabilities import Capabilities as VoiceCapabilities
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway

API_VERSION = 1


@dataclass(frozen=True)
class PluginContext:
    """Resolved model settings and the host's cancellable subprocess driver.

    For a plugin that declares `loras`, the host reads the `[[<backend_id>.loras]]` tables of
    its section. `capabilities` is then the declared record with those LoRAs offered by id,
    and `lora_paths` maps each id to its file. The gateway returns `capabilities`, so the page
    and the API see the ids and never a path. For any other plugin, `capabilities` is None.
    """

    settings: Mapping[str, Any]
    run_process: Callable[..., Any]
    capabilities: VideoCapabilities | None = None
    lora_paths: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelPlugin:
    """An entry point exports this record, not a loaded model or engine.

    The capability backend_id must equal its entry point name, globally unique
    across Image, Video and Voice. The factory returns that media's gateway.
    A model with no rewriter leaves it unset, so Rewrite is hidden for that model.
    """

    capabilities: ImageCapabilities | VideoCapabilities | VoiceCapabilities
    create: Callable[[PluginContext], ImageBackendGateway | VideoBackendGateway | VoiceBackendGateway]
    rewriter: Callable[[PluginContext], PromptRewriterGateway] | None = None
    api_version: int = API_VERSION
    loras: bool = False
    """True when the engine takes any LoRA file. The host then reads the plugin's LoRA tables
    and offers them, as it does for a built-in model. Only a video model can set it, and its
    capability record then declares no LoRAs of its own. It comes last, so a record that gives
    `api_version` by position keeps its meaning."""


__all__ = ["API_VERSION", "ModelPlugin", "PluginContext", "PromptRewrite", "PromptRewriterGateway"]
