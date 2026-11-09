"""Composition factory for voice/auk."""

from studio.l3_interface_adapters.gateways.voice.auk.auk_backend_gateway import AukBackendGateway
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.model_factories.voice.auk_runtime import _auk_child


def voice_auk_backend(config: Config) -> AukBackendGateway:
    return AukBackendGateway(_auk_child(config, "auk_base", "base"))
