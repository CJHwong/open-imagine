"""Composition factory for image/qwen21_cuda: the Turbo checkpoint on an NVIDIA GPU."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.qwen21_cuda.qwen21_cuda_backend_gateway import (
    Qwen21CudaBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.qwen21_cuda.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

DEFAULT_MODEL = "Qwen/Qwen-Image-2.1-Turbo"
QUANTIZERS = {"nvfp4", "bf16"}


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("Qwen-Image-2.1-Turbo on CUDA needs uv on PATH.")
    return found


def qwen21_cuda_backend(config: ModelConfigurationGateway, **_):
    settings = config.backend("qwen21_turbo_cuda")
    model = str(settings.get("model", DEFAULT_MODEL))
    quantize = str(settings.get("quantize", "nvfp4"))
    if quantize not in QUANTIZERS:
        raise ModelConfigurationError(
            f"[qwen21_turbo_cuda].quantize is {quantize!r}; it must be one of {', '.join(sorted(QUANTIZERS))}."
        )
    script = Path(__file__).parent.parent / "qwen_cuda_runtime" / "qwen21_cuda_child.py"
    command = [
        uv_launcher(),
        "run",
        "--python",
        "3.12",
        "--script",
        str(script),
        "--model",
        model,
        "--quantize",
        quantize,
    ]
    return Qwen21CudaBackendGateway(StdioChild(command), badge=quantize)


PROVIDER = ModelProvider(
    "qwen21_turbo_cuda",
    "image",
    qwen21_cuda_backend,
    engine="cuda",
    storage_assets=storage_assets,
    storage_name="Qwen-Image-2.1-Turbo",
)
