"""Construct the shared AuK child process."""

from pathlib import Path

from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l4_frameworks_and_drivers.config import Config


def _auk_child(config: Config, backend_id: str, variant: str) -> StdioChild:
    child_path = Path(__file__).resolve().parents[3] / "l3_interface_adapters/gateways/voice/auk_runtime/auk_child.py"
    settings = {**config.backend("auk"), **config.backend(backend_id)}
    return StdioChild(["uv", "run", "--script", str(settings.get("child_script", child_path)), "--variant", variant])
