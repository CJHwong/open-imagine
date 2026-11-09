"""Registration for a plugin that supplies its own backend factory."""

from collections.abc import Callable
from dataclasses import dataclass

from studio.l1_entities.capabilities import Capabilities as ImageCapabilities
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.voice_capabilities import Capabilities as VoiceCapabilities
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.plugins.api_version import MODEL_PLUGIN_API_VERSION
from studio.plugins.model_factory_context import ModelFactoryContext


@dataclass(frozen=True)
class GatewayModelRegistration:
    """An entry point exports this record, not a loaded model or engine.

    The capability backend_id must equal its entry point name, globally unique
    across Image, Video and Voice. The factory returns that media's gateway.
    A model with no rewriter leaves it unset, so Rewrite is hidden for that model.
    """

    capabilities: ImageCapabilities | VideoCapabilities | VoiceCapabilities
    create: Callable[[ModelFactoryContext], ImageBackendGateway | VideoBackendGateway | VoiceBackendGateway]
    rewriter: Callable[[ModelFactoryContext], PromptRewriterGateway] | None = None
    api_version: int = MODEL_PLUGIN_API_VERSION
