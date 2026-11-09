"""Construct backend gateways for registrations that supply their own runtime."""

from studio.l1_entities.capabilities import Capabilities as ImageCapabilities
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l3_interface_adapters.gateways.image.stub_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stub_prompt_rewriter_gateway import StubPromptRewriterGateway
from studio.l3_interface_adapters.gateways.video.stub_video_backend_gateway import StubVideoBackendGateway
from studio.l3_interface_adapters.gateways.voice.stub_voice_backend_gateway import StubVoiceBackendGateway
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.model_registration.catalog import ModelRegistrationCatalog
from studio.l4_frameworks_and_drivers.model_registration.factory_context import create_context
from studio.plugins import GatewayModelRegistration

GATEWAYS = {"image": ImageBackendGateway, "video": VideoBackendGateway, "voice": VoiceBackendGateway}


class ModelBackendFactory:
    """Construct gateways and rewriters from a factory registration, without discovery."""

    def __init__(self, catalog: ModelRegistrationCatalog):
        self._catalog = catalog

    def build(self, kind: str, name: str, config: Config, stub: bool = False, **_):
        registration = self._registration(kind, name)
        if stub:
            capabilities = registration.capabilities
            if isinstance(capabilities, ImageCapabilities):
                return StubBackendGateway(capabilities)
            if isinstance(capabilities, VideoCapabilities):
                return StubVideoBackendGateway(capabilities)
            return StubVoiceBackendGateway(capabilities=capabilities)
        try:
            gateway = registration.create(create_context(config, name))
            if not isinstance(gateway, GATEWAYS[kind]) or gateway.capabilities() != registration.capabilities:
                raise ValueError("factory must return its media gateway with the declared capabilities")
            return gateway
        except Exception as error:
            raise ConfigError(f"Cannot construct {kind} model plugin {name}: {error}") from error

    def rewriter(self, kind: str, name: str, config: Config, stub: bool = False) -> PromptRewriterGateway:
        factory = self._registration(kind, name).rewriter
        if factory is None:
            return NoPromptRewriterGateway()
        if stub:
            return StubPromptRewriterGateway()
        try:
            rewriter = factory(create_context(config, name))
            if not isinstance(rewriter, PromptRewriterGateway):
                raise ValueError("rewriter must return a PromptRewriterGateway")
            return rewriter
        except Exception as error:
            raise ConfigError(f"Cannot construct {kind} rewriter plugin {name}: {error}") from error

    def _registration(self, kind: str, name: str) -> GatewayModelRegistration:
        registration = self._catalog.declaration(kind, name)
        if not isinstance(registration, GatewayModelRegistration):
            raise ConfigError(f"{name} runs on the host's own engine, so the host builds it and its rewriter.")
        return registration
