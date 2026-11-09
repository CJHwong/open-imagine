"""Composition factory for voice/auk_flash."""

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.voice.auk_flash.auk_flash_backend_gateway import AukFlashBackendGateway
from studio.l3_interface_adapters.gateways.voice.auk_flash.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.voice.auk_runtime.construction import _auk_child


def voice_auk_flash_backend(config: ModelConfigurationGateway, **_) -> AukFlashBackendGateway:
    return AukFlashBackendGateway(_auk_child(config, "auk", "flash"))


PROVIDER = ModelProvider(
    "auk", "voice", voice_auk_flash_backend, storage_assets=storage_assets, storage_name="AuK Flash"
)
