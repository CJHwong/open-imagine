"""Composition factory for video/ltx23."""

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.video.ltx23.ltx23_backend_gateway import Ltx23BackendGateway
from studio.l3_interface_adapters.gateways.video.ltx_runtime.construction import (
    _mlx_video_runner,
    validate_lora_section,
)
from studio.l3_interface_adapters.gateways.video.ltx_runtime.rewriter_configuration import build_rewriter, enhancer

LORA_POLICY = LoraTablePolicy(mode_scoped=False)


def ltx23_mlx_backend(
    config: ModelConfigurationGateway, enhanced_prompt=None, *, execute_process, services=None, **_
) -> Ltx23BackendGateway:
    validate_lora_section(config, "ltx23_mlx")
    loras = parse_lora_tables(config.backend("ltx23_mlx"), "ltx23_mlx", policy=LORA_POLICY)
    model = str(config.backend("mlx_video").get("model_ltx23", ""))
    if services is not None and enhanced_prompt is None:
        enhanced_prompt = enhancer(config, services).is_enhanced
    runner = _mlx_video_runner(
        config,
        model,
        "model_ltx23",
        execute_process=execute_process,
        keyframe_two_stage=True,
        enhanced_prompt=enhanced_prompt,
        loras=loras,
    )
    return Ltx23BackendGateway(runner, loras)


PROVIDER = ModelProvider("ltx23_mlx", "video", ltx23_mlx_backend, rewriter=build_rewriter)
