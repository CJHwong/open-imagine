"""Composition factory for video/ltx25."""

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.video.ltx25.ltx25_backend_gateway import Ltx25BackendGateway
from studio.l3_interface_adapters.gateways.video.ltx25.memory_estimate import estimate_peak_gib
from studio.l3_interface_adapters.gateways.video.ltx25.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.video.ltx_runtime.construction import (
    _mlx_video_runner,
    validate_lora_section,
)
from studio.l3_interface_adapters.gateways.video.ltx_runtime.rewriter_configuration import build_rewriter, enhancer

LORA_POLICY = LoraTablePolicy(mode_scoped=False)


def ltx25_mlx_backend(
    config: ModelConfigurationGateway, enhanced_prompt=None, *, execute_process, services=None, **_
) -> Ltx25BackendGateway:
    # The engine's settings are shared under [mlx_video]; each model's LoRAs are its own.
    validate_lora_section(config, "ltx25_mlx")
    loras = parse_lora_tables(config.backend("ltx25_mlx"), "ltx25_mlx", policy=LORA_POLICY)
    model = str(config.backend("mlx_video").get("model_ltx25", ""))
    if services is not None and enhanced_prompt is None:
        enhanced_prompt = enhancer(config, services).is_enhanced
    runner = _mlx_video_runner(
        config,
        model,
        "model_ltx25",
        execute_process=execute_process,
        keyframe_two_stage=False,
        enhanced_prompt=enhanced_prompt,
        loras=loras,
    )
    return Ltx25BackendGateway(runner, loras)


def memory_estimator(config):
    return estimate_peak_gib


PROVIDER = ModelProvider(
    "ltx25_mlx",
    "video",
    ltx25_mlx_backend,
    estimator=memory_estimator,
    rewriter=build_rewriter,
    storage_assets=storage_assets,
    storage_name="LTX-2.5",
)
