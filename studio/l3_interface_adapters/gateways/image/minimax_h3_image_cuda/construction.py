"""Composition factory for image/minimax_h3_image_cuda."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.minimax_h3_image_cuda_backend_gateway import (
    MinimaxH3ImageCudaBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

DEFAULT_MODEL = "MiniMaxAI/MiniMax-H3-Image"
DEFAULT_PACK_DIR = "~/.cache/open-imagine/h3-pack"
"""Where the quantized weights are kept, built on the first run of each quantizer."""
QUANTIZERS = {"nvfp4", "fp8", "bf16"}


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("MiniMax H3-Image on CUDA needs uv on PATH.")
    return found


def minimax_h3_image_cuda_backend(config: ModelConfigurationGateway, **_):
    settings = config.backend("minimax_h3_image_cuda")
    model = str(settings.get("model", DEFAULT_MODEL))
    quantize = str(settings.get("quantize", "nvfp4"))
    if quantize not in QUANTIZERS:
        raise ModelConfigurationError(
            f"[minimax_h3_image_cuda].quantize is {quantize!r}; it must be one of {', '.join(sorted(QUANTIZERS))}."
        )
    script = Path(__file__).with_name("minimax_h3_image_cuda_child.py")
    pack_dir = str(settings.get("pack_dir", DEFAULT_PACK_DIR))
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
        "--pack-dir",
        str(Path(pack_dir).expanduser()),
    ]
    return MinimaxH3ImageCudaBackendGateway(StdioChild(command), badge=quantize)


PROVIDER = ModelProvider(
    "minimax_h3_image_cuda",
    "image",
    minimax_h3_image_cuda_backend,
    engine="cuda",
    storage_assets=storage_assets,
    storage_name="MiniMax-H3-Image",
)
