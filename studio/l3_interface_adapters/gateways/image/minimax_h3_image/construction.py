"""Composition factory for image/minimax_h3_image."""

from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.boundaries.process_gateway import ProcessGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.h3_image_pe_rewriter import H3ImagePeRewriter
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.memory_estimate import estimate_peak_gib
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.minimax_h3_image_backend_gateway import (
    MinimaxH3ImageBackendGateway,
    uv_launcher,
)
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import reject_lora_tables
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway


def minimax_h3_image_backend(
    config: ModelConfigurationGateway, *, execute_process: ProcessGateway, **_
) -> MinimaxH3ImageBackendGateway:
    """The weights are stored at int8 and the engine reads no other level, so a quantize
    other than 8 is refused rather than shown and then ignored."""
    settings = config.backend("minimax_h3_image")
    reject_lora_tables(settings, "minimax_h3_image")
    if "quantize" in settings and settings["quantize"] != 8:
        raise ModelConfigurationError(
            "[minimax_h3_image] runs its weights at int8, as they are stored. Remove its quantize, or use 8."
        )
    return MinimaxH3ImageBackendGateway(
        config.required("minimax_h3_image", "model_dir"),
        execute_process=execute_process,
    )


def build_rewriter(config: ModelConfigurationGateway, backend_id: str, **_):
    """The model's own prompt enhancer, run as a script child, or none when no pack is named.

    A settings file written before the enhancer existed names no pack, and that studio starts
    as it did, with no Rewrite toggle, rather than refusing to boot.
    """
    pack = config.backend("minimax_h3_image").get("rewrite_model_dir")
    if not pack:
        return NoPromptRewriterGateway()
    child = Path(__file__).with_name("h3_image_pe_child.py")
    command = [uv_launcher(), "run", "--script", str(child), "--model-dir", str(Path(str(pack)).expanduser())]
    prompts = config.backend("minimax_h3_image").get("rewrite_prompt_dir")
    if prompts:
        command += ["--prompt-dir", str(Path(str(prompts)).expanduser())]
    return H3ImagePeRewriter(command)


def memory_estimator(config):
    return estimate_peak_gib


PROVIDER = ModelProvider(
    "minimax_h3_image",
    "image",
    minimax_h3_image_backend,
    estimator=memory_estimator,
    rewriter=build_rewriter,
    storage_assets=storage_assets,
    storage_name="MiniMax H3-Image",
)
