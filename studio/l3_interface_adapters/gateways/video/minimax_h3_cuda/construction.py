"""Composition factory for video/minimax_h3_cuda."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.capabilities import FLASH_CAPABILITIES
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.minimax_h3_cuda_backend_gateway import (
    MinimaxH3CudaBackendGateway,
    flash_schedule,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.storage_assets import (
    DEFAULT_MODEL,
    flash_storage_assets,
    storage_assets,
)


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("MiniMax H3 on CUDA needs uv on PATH.")
    return found


def child_command(config: ModelConfigurationGateway) -> list[str]:
    settings = config.backend("minimax_h3_cuda")
    script = Path(__file__).with_name("minimax_h3_cuda_child.py")
    command = [uv_launcher(), "run", "--python", "3.12", "--script", str(script)]
    command += ["--model", str(settings.get("model", DEFAULT_MODEL))]
    if settings.get("revision"):
        command += ["--revision", str(settings["revision"])]
    return command


def minimax_h3_cuda_backend(config: ModelConfigurationGateway, **_):
    return MinimaxH3CudaBackendGateway(StdioChild(child_command(config)))


def minimax_h3_flash_cuda_backend(config: ModelConfigurationGateway, **_):
    """Flash runs on the child of base H3 and reads the encoder and the VAEs of the model that the
    [minimax_h3_cuda] section names. Only its two transformers and its schedule differ."""
    command = [*child_command(config), "--flash"]
    return MinimaxH3CudaBackendGateway(StdioChild(command), FLASH_CAPABILITIES, flash_schedule)


PROVIDER = ModelProvider(
    "minimax_h3_cuda",
    "video",
    minimax_h3_cuda_backend,
    engine="cuda",
    storage_assets=storage_assets,
    storage_name="MiniMax H3",
    # A studio idle with the model loaded had 62 GiB less free memory than before its first
    # clip, on the DGX Spark on 2026-11-20. The weights alone are 56.3 GiB.
    resident_gib=62.0,
)

# PENDING MEASUREMENT: base H3's figure until a studio run measures Flash idle.
FLASH_RESIDENT_GIB = 62.0

FLASH_PROVIDER = ModelProvider(
    "minimax_h3_flash_cuda",
    "video",
    minimax_h3_flash_cuda_backend,
    engine="cuda",
    storage_assets=flash_storage_assets,
    storage_name="HyperFlow H3 Flash",
    resident_gib=FLASH_RESIDENT_GIB,
)
