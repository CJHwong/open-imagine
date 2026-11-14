"""Composition factory for music/yue2_cuda."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.music.yue2_cuda.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.music.yue2_cuda.yue2_cuda_backend_gateway import Yue2CudaBackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

DEFAULT_MODEL = "m-a-p/YuE2-3B"


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("YuE2 on CUDA needs uv on PATH.")
    return found


def yue2_cuda_backend(config: ModelConfigurationGateway, **_):
    settings = config.backend("yue2_cuda")
    model = str(settings.get("model", DEFAULT_MODEL))
    script = Path(__file__).with_name("yue2_cuda_child.py")
    command = [uv_launcher(), "run", "--python", "3.12", "--script", str(script), "--model", model]
    return Yue2CudaBackendGateway(StdioChild(command))


PROVIDER = ModelProvider(
    "yue2_cuda",
    "music",
    yue2_cuda_backend,
    engine="cuda",
    storage_assets=storage_assets,
    storage_name="YuE2",
)
