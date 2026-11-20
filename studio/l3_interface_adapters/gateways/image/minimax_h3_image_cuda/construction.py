"""Composition factory for image/minimax_h3_image_cuda."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_asset import ModelAsset
from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import h3_pack_spec
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.minimax_h3_image_cuda_backend_gateway import (
    MinimaxH3ImageCudaBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.storage_assets import storage_assets_for
from studio.l3_interface_adapters.gateways.image.shared.h3_image_pe_rewriter import H3ImagePeRewriter
from studio.l3_interface_adapters.gateways.image.shared.rewrite_precision import rewrite_precision
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

DEFAULT_MODEL = "MiniMaxAI/MiniMax-H3-Image"
# A pack is one model at one precision, so each precision keeps its own folder. Sharing one
# let a prepare of the NVFP4 entry overwrite the FP8 entry's pack on 2026-11-19. FP8 keeps
# the folder it always had, so an existing FP8 pack stays where it is.
DEFAULT_PACK_DIRS = {
    "fp8": "~/.cache/open-imagine/h3-pack",
    "nvfp4": "~/.cache/open-imagine/h3-pack-nvfp4",
}


def pack_root(settings, quantize: str) -> Path:
    """The folder that holds this precision's packs, unless the section names its own. A
    bf16 child reads no pack, so it takes the FP8 folder only to fill its argument."""
    default = DEFAULT_PACK_DIRS.get(quantize, DEFAULT_PACK_DIRS["fp8"])
    return Path(str(settings.get("pack_dir", default))).expanduser()


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
# fp8 was 70.3 GB of packed weights, fp8 in the encoder and the transformer, plus the run's
# own buffers; a studio idle with it loaded had 77.4 GiB less free memory than before it
# started, on 2026-11-19. Dropping the encoder layers and head that H3 never reads took
# 8.4 GiB off that: 68.8 against 60.4 GiB, measured the same way on the same day.
# The NVFP4 entry was dropped on 2026-11-20: it ran faster at large sizes and held less memory,
# but its pictures were too grainy to use. `quantize = "nvfp4"` still selects that build.
BUILDS = {
    "minimax_h3_image_cuda": ("MiniMax H3-Image", "fp8", 65.0),
}


def pack_assets_for(backend_id: str):
    """The pack a run reads, where the child writes it: the pack root, then the model's
    folder, with the manifest the child will check. A bf16 run quantizes nothing, so it
    reads no pack."""
    _, default_quantize, _ = BUILDS[backend_id]

    def assets(config: ModelConfigurationGateway) -> tuple[ModelAsset, ...]:
        settings = config.backend(backend_id)
        quantize = str(settings.get("quantize", default_quantize))
        if quantize == "bf16":
            return ()
        model = str(settings.get("model", DEFAULT_MODEL))

        def expected():
            return h3_pack_spec.expected_manifest(model, quantize, h3_pack_spec.source_revision(model))

        folder = str(pack_root(settings, quantize) / model.replace("/", "--"))
        return (ModelAsset("Pack", folder, "pack", expected=expected),)

    return assets


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
            str(pack_root(settings, quantize)),
        ]
        # Only a prepare starts the child that may build a pack; a run's child refuses to.
        return MinimaxH3ImageCudaBackendGateway(
            StdioChild(command),
            prepare_child=StdioChild([*command, "--may-build"]),
            backend_id=backend_id,
            name=name,
            badge=quantize,
        )

    return build


PROVIDER = ModelProvider(
    "minimax_h3_image_cuda",
    "image",
    backend_factory("minimax_h3_image_cuda"),
    engine="cuda",
    storage_assets=storage_assets_for("minimax_h3_image_cuda"),
    ready_assets=pack_assets_for("minimax_h3_image_cuda"),
    storage_name="MiniMax H3-Image",
    storage_roots=tuple(os.path.expanduser(folder) for folder in DEFAULT_PACK_DIRS.values()),
    rewriter=build_rewriter,
    resident_gib=BUILDS["minimax_h3_image_cuda"][2],
)
