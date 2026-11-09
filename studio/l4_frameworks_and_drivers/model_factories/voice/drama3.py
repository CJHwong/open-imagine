"""Composition factory for voice/drama3."""

from pathlib import Path

from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.voice.drama3.drama3_backend_gateway import Drama3BackendGateway
from studio.l4_frameworks_and_drivers.config import Config


def voice_drama_backend(config: Config):
    child_path = Path(__file__).resolve().parents[3] / "l3_interface_adapters/gateways/voice/drama3/drama3_child.py"
    settings = config.backend("drama3")
    script = str(settings.get("child_script", child_path))
    python = settings.get("python_path")
    command = [str(python), script] if python else ["uv", "run", "--script", script]
    return Drama3BackendGateway(StdioChild(command))
