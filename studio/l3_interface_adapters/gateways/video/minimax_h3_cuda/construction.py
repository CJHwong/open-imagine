"""Composition factory for video/minimax_h3_cuda."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.minimax_h3_cuda_backend_gateway import (
    MinimaxH3CudaBackendGateway,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.storage_assets import DEFAULT_MODEL, storage_assets


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("MiniMax H3 on CUDA needs uv on PATH.")
    return found


def minimax_h3_cuda_backend(config: ModelConfigurationGateway, **_):
    settings = config.backend("minimax_h3_cuda")
    script = Path(__file__).with_name("minimax_h3_cuda_child.py")
    command = [uv_launcher(), "run", "--python", "3.12", "--script", str(script)]
    command += ["--model", str(settings.get("model", DEFAULT_MODEL))]
    if settings.get("revision"):
        command += ["--revision", str(settings["revision"])]
    return MinimaxH3CudaBackendGateway(StdioChild(command))


PROVIDER = ModelProvider(
    "minimax_h3_cuda",
    "video",
    minimax_h3_cuda_backend,
    engine="cuda",
    storage_assets=storage_assets,
    storage_name="MiniMax H3",
    # The encoder and both transformers in NVFP4 held 56.3 GiB on the DGX Spark, and a run
    # peaked at 64.0 GiB, measured through diffusers directly on 2026-11-20.
    resident_gib=60.0,
)
