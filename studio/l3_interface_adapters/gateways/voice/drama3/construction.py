"""Composition factory for voice/drama3."""

from pathlib import Path

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.voice.drama3.drama3_backend_gateway import Drama3BackendGateway
from studio.l3_interface_adapters.gateways.voice.drama3.memory_estimate import estimate_peak_gib


def voice_drama_backend(config: ModelConfigurationGateway, **_):
    child_path = Path(__file__).with_name("drama3_child.py")
    settings = config.backend("drama3")
    script = str(settings.get("child_script", child_path))
    python = settings.get("python_path")
    command = [str(python), script] if python else ["uv", "run", "--script", script]
    return Drama3BackendGateway(StdioChild(command))


def memory_estimator(config):
    return estimate_peak_gib


PROVIDER = ModelProvider("drama3", "voice", voice_drama_backend, estimator=memory_estimator)
