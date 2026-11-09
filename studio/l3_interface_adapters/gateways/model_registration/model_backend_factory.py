"""Construct backend gateways for registrations that supply their own runtime."""

from dataclasses import replace
from types import MappingProxyType
from typing import cast

from studio.l1_entities.capabilities import Capabilities as ImageCapabilities
from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l2_use_cases.boundaries.voice_backend_gateway import VoiceBackendGateway
from studio.l3_interface_adapters.gateways.lora_files import LoraFiles
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.model_registration.catalog import ModelRegistrationCatalog
from studio.l3_interface_adapters.gateways.model_registration.factory_context import create_context
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stub.image_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.stub.prompt_rewriter_gateway import StubPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stub.video_backend_gateway import StubVideoBackendGateway
from studio.l3_interface_adapters.gateways.stub.voice_backend_gateway import StubVoiceBackendGateway
from studio.plugins import GatewayModelRegistration

GATEWAYS = {"image": ImageBackendGateway, "video": VideoBackendGateway, "voice": VoiceBackendGateway}


LORA_POLICY = LoraTablePolicy(mode_scoped=False)


class ModelBackendFactory:
    """Construct gateways and rewriters from a factory registration, without discovery."""

    def __init__(self, catalog: ModelRegistrationCatalog, execute_process):
        self._execute_process = execute_process
        self._catalog = catalog

    def build(self, kind: str, name: str, config: ModelConfigurationGateway, stub: bool = False, **_):
        registration = self._registration(kind, name)
        capabilities = registration.capabilities
        loras = LoraFiles()
        if registration.loras:
            loras = parse_lora_tables(config.backend(name), name, policy=LORA_POLICY)
            capabilities = loras.offer_video(cast(VideoCapabilities, registration.capabilities))
        if stub:
            if isinstance(capabilities, ImageCapabilities):
                return StubBackendGateway(capabilities)
            if isinstance(capabilities, VideoCapabilities):
                return StubVideoBackendGateway(capabilities)
            return StubVoiceBackendGateway(capabilities=capabilities)
        context = create_context(config, name, self._execute_process)
        if registration.loras:
            paths = MappingProxyType({item.lora.id: item.path for item in loras.files})
            context = replace(context, capabilities=capabilities, lora_paths=paths)
        try:
            gateway = registration.create(context)
            if not isinstance(gateway, GATEWAYS[kind]) or gateway.capabilities() != capabilities:
                raise ValueError("factory must return its media gateway with the declared capabilities")
            return gateway
        except Exception as error:
            raise ModelConfigurationError(f"Cannot construct {kind} model plugin {name}: {error}") from error

    def rewriter(
        self, kind: str, name: str, config: ModelConfigurationGateway, stub: bool = False, **_
    ) -> PromptRewriterGateway:
        factory = self._registration(kind, name).rewriter
        if factory is None:
            return NoPromptRewriterGateway()
        if stub:
            return StubPromptRewriterGateway()
        try:
            rewriter = factory(create_context(config, name, self._execute_process))
            if not isinstance(rewriter, PromptRewriterGateway):
                raise ValueError("rewriter must return a PromptRewriterGateway")
            return rewriter
        except Exception as error:
            raise ModelConfigurationError(f"Cannot construct {kind} rewriter plugin {name}: {error}") from error

    def _registration(self, kind: str, name: str) -> GatewayModelRegistration:
        registration = self._catalog.declaration(kind, name)
        if not isinstance(registration, GatewayModelRegistration):
            raise ModelConfigurationError(
                f"{name} runs on the host's own engine, so the host builds it and its rewriter."
            )
        return registration
