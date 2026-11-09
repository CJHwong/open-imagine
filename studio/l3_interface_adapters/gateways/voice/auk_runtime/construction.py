"""Construct the shared AuK child process."""

from pathlib import Path

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild


def _auk_child(config: ModelConfigurationGateway, backend_id: str, variant: str) -> StdioChild:
    child_path = Path(__file__).with_name("auk_child.py")
    settings = {**config.backend("auk"), **config.backend(backend_id)}
    return StdioChild(["uv", "run", "--script", str(settings.get("child_script", child_path)), "--variant", variant])
