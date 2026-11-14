"""Composition factory for voice/drama3_cuda."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.drama3_cuda_backend_gateway import (
    Drama3CudaBackendGateway,
)
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.storage_assets import storage_assets

DEFAULT_CHECKPOINT = "fishaudio/drama-3"


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("Drama-3 on CUDA needs uv on PATH.")
    return found


def voice_drama_cuda_backend(config: ModelConfigurationGateway, **_):
    settings = config.backend("drama3_cuda")
    checkpoint = str(settings.get("checkpoint", DEFAULT_CHECKPOINT))
    script = Path(__file__).with_name("drama3_cuda_child.py")
    command = [uv_launcher(), "run", "--python", "3.12", "--script", str(script), "--checkpoint", checkpoint]
    return Drama3CudaBackendGateway(StdioChild(command))


PROVIDER = ModelProvider(
    "drama3_cuda",
    "voice",
    voice_drama_cuda_backend,
    engine="cuda",
    storage_assets=storage_assets,
    storage_name="Drama-3",
)
