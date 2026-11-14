"""Composition factory for video/ltx25_cuda."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.ltx25_cuda_backend_gateway import Ltx25CudaBackendGateway
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.storage_assets import storage_assets

DEFAULT_MODEL = "Lightricks/LTX-2.5-Diffusers"


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("LTX-2.5 on CUDA needs uv on PATH.")
    return found


def ltx25_cuda_backend(config: ModelConfigurationGateway, **_):
    settings = config.backend("ltx25_cuda")
    model = str(settings.get("model", DEFAULT_MODEL))
    script = Path(__file__).with_name("ltx25_cuda_child.py")
    command = [uv_launcher(), "run", "--python", "3.12", "--script", str(script), "--model", model]
    return Ltx25CudaBackendGateway(StdioChild(command))


PROVIDER = ModelProvider(
    "ltx25_cuda",
    "video",
    ltx25_cuda_backend,
    engine="cuda",
    storage_assets=storage_assets,
    storage_name="LTX-2.5",
)
