"""Validate one public model-registration format."""

from studio.l1_entities.capabilities import Capabilities as ImageCapabilities
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.voice_capabilities import Capabilities as VoiceCapabilities
from studio.plugins import API_VERSION, GatewayModelRegistration

CAPABILITIES = {"image": ImageCapabilities, "video": VideoCapabilities, "voice": VoiceCapabilities}


def validate(registration, kind: str, name: str) -> None:
    if not isinstance(registration, GatewayModelRegistration) or registration.api_version != API_VERSION:
        raise ValueError(f"expected GatewayModelRegistration API version {API_VERSION}")
    if not isinstance(registration.capabilities, CAPABILITIES[kind]) or registration.capabilities.backend_id != name:
        raise ValueError(f"expected {kind} capabilities with backend_id {name!r}")
    if not callable(registration.create) or (registration.rewriter is not None and not callable(registration.rewriter)):
        raise ValueError("create and optional rewriter must be factories")
    if not isinstance(registration.loras, bool):
        raise ValueError("loras must be True or False")
    if registration.loras and kind != "video":
        raise ValueError("only a video model takes LoRA tables in this version")
    if registration.loras and registration.capabilities.loras:
        raise ValueError("a model that takes LoRA tables declares no LoRAs of its own")
