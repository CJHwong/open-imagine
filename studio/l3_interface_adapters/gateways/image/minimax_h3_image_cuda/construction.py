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
from studio.l3_interface_adapters.gateways.image.shared.h3_image_pe_rewriter import H3ImagePeRewriter
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

DEFAULT_MODEL = "MiniMaxAI/MiniMax-H3-Image"
DEFAULT_PACK_DIR = "~/.cache/open-imagine/h3-pack"
# The release's own prompt enhancer, the same one the MLX setup converts. A Hub repo id or a
# local folder that already holds it; empty or absent hides the page's Rewrite toggle.
DEFAULT_REWRITE_MODEL = "MiniMaxAI/MiniMax-H3-Image-PE"
"""Where the quantized weights are kept, built on the first run of each quantizer."""
QUANTIZERS = {"nvfp4", "fp8", "bf16"}


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("MiniMax H3-Image on CUDA needs uv on PATH.")
    return found


def build_rewriter(config: ModelConfigurationGateway, backend_id: str, **_):
    """The enhancer child, when the section names one.

    The gateway is the MLX one: it drives any child that answers the same job with the same
    reply, and the two ports keep that protocol identical.
    """
    settings = config.backend(backend_id)
    model = str(settings.get("rewrite_model", "") or "")
    if not model:
        return NoPromptRewriterGateway()
    script = Path(__file__).with_name("h3_image_pe_cuda_child.py")
    return H3ImagePeRewriter([uv_launcher(), "run", "--python", "3.12", "--script", str(script), "--model", model])


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
    rewriter=build_rewriter,
    # 51 GB of packed weights plus the vae and the run's own buffers, DGX Spark, 2026-11-15.
    resident_gib=55.0,
)
