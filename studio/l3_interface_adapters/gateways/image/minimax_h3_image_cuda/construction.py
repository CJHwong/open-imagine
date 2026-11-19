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
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.storage_assets import storage_assets_for
from studio.l3_interface_adapters.gateways.image.shared.h3_image_pe_rewriter import H3ImagePeRewriter
from studio.l3_interface_adapters.gateways.image.shared.rewrite_precision import rewrite_precision
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
    precision = rewrite_precision(config, backend_id)
    command = [uv_launcher(), "run", "--python", "3.12", "--script", str(script), "--model", model]
    return H3ImagePeRewriter([*command, "--quantize", precision])


# backend id -> (name in the picker, the build this entry runs, its resident memory in GiB).
# fp8 is 70.3 GB of packed weights, fp8 in the encoder and the transformer, plus the run's
# own buffers; a studio idle with it loaded had 77.4 GiB less free memory than before it
# started, on 2026-11-19. The NVFP4 pack is 38 GB on disk, so it holds less. Both read on
# the same basis. The NVFP4 load peaks well
# above its resident figure: the run that loaded it from the pack dropped free memory by
# 104.21 GiB on 2026-11-15, because the weights travel through host memory.
BUILDS = {
    "minimax_h3_image_cuda": ("MiniMax H3-Image (CUDA)", "fp8", 73.0),
    "minimax_h3_image_cuda_nvfp4": ("MiniMax H3-Image (CUDA, NVFP4)", "nvfp4", 40.0),
}


def backend_factory(backend_id: str):
    """The factory for one entry. The entry names the build it runs, and its own section
    keeps the model, the packing and the enhancer."""
    name, default_quantize, _ = BUILDS[backend_id]

    def build(config: ModelConfigurationGateway, **_):
        settings = config.backend(backend_id)
        model = str(settings.get("model", DEFAULT_MODEL))
        quantize = str(settings.get("quantize", default_quantize))
        if quantize not in QUANTIZERS:
            raise ModelConfigurationError(
                f"[{backend_id}].quantize is {quantize!r}; it must be one of {', '.join(sorted(QUANTIZERS))}."
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
        return MinimaxH3ImageCudaBackendGateway(StdioChild(command), backend_id=backend_id, name=name, badge=quantize)

    return build


PROVIDER = ModelProvider(
    "minimax_h3_image_cuda",
    "image",
    backend_factory("minimax_h3_image_cuda"),
    engine="cuda",
    storage_assets=storage_assets_for("minimax_h3_image_cuda"),
    storage_name="MiniMax-H3-Image",
    rewriter=build_rewriter,
    resident_gib=BUILDS["minimax_h3_image_cuda"][2],
)

NVFP4_PROVIDER = ModelProvider(
    "minimax_h3_image_cuda_nvfp4",
    "image",
    backend_factory("minimax_h3_image_cuda_nvfp4"),
    engine="cuda",
    storage_assets=storage_assets_for("minimax_h3_image_cuda_nvfp4"),
    storage_name="MiniMax-H3-Image",
    rewriter=build_rewriter,
    resident_gib=BUILDS["minimax_h3_image_cuda_nvfp4"][2],
)
