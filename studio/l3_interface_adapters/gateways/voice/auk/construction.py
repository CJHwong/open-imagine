"""Composition factory for voice/auk."""

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.voice.auk.auk_backend_gateway import AukBackendGateway
from studio.l3_interface_adapters.gateways.voice.auk.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.voice.auk_runtime.construction import _auk_child


def voice_auk_backend(config: ModelConfigurationGateway, **_) -> AukBackendGateway:
    return AukBackendGateway(_auk_child(config, "auk_base", "base"))


PROVIDER = ModelProvider("auk_base", "voice", voice_auk_backend, storage_assets=storage_assets, storage_name="AuK")
