"""Composition factory for voice/auk_flash."""

from studio.l3_interface_adapters.gateways.voice.auk_flash.auk_flash_backend_gateway import AukFlashBackendGateway
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.model_factories.voice.auk_runtime import _auk_child


def voice_auk_flash_backend(config: Config) -> AukFlashBackendGateway:
    return AukFlashBackendGateway(_auk_child(config, "auk", "flash"))
