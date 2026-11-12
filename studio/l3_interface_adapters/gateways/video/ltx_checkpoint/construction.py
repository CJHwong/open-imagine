"""Composition factory for video/ltx_checkpoint."""

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.video.ltx_checkpoint.ltx_checkpoint_backend_gateway import (
    LtxCheckpointBackendGateway,
)
from studio.l3_interface_adapters.gateways.video.ltx_runtime.construction import (
    _mlx_video_runner,
    validate_lora_section,
)
from studio.l3_interface_adapters.gateways.video.ltx_runtime.rewriter_configuration import enhancer
from studio.l3_interface_adapters.gateways.video.shared.capabilities import ltx_checkpoint_capabilities
from studio.plugins.ltx_checkpoint_registration import LtxCheckpointRegistration

LORA_POLICY = LoraTablePolicy(mode_scoped=False)


def ltx_checkpoint_backend(
    config: ModelConfigurationGateway,
    pack: LtxCheckpointRegistration,
    enhanced_prompt=None,
    *,
    execute_process,
    services=None,
    **_,
) -> LtxCheckpointBackendGateway:
    """A pack that a plugin names, run by the base packs' runner, with the same enhancer.

    The folder and the LoRAs come from the plugin's own section. The engine's settings stay
    under [mlx_video]. The gateway checks the folder when a run starts, as the base packs check
    their own setting: `--all-backends` offers every installed pack, with or without a section.
    """
    pack_dir = str(config.backend(pack.backend_id).get("pack_dir", ""))
    try:
        capabilities = ltx_checkpoint_capabilities(
            pack.backend_id,
            pack.name,
            pack.family,
            description=pack.description,
            precision=pack.precision,
            edit=pack.edit,
            audio=pack.audio,
            fast_mode=pack.fast_mode,
        )
    except ValueError as error:
        raise ModelConfigurationError(f"Cannot build the LTX pack {pack.backend_id}: {error}") from None
    validate_lora_section(config, pack.backend_id)
    loras = parse_lora_tables(config.backend(pack.backend_id), pack.backend_id, policy=LORA_POLICY)
    if services is not None and enhanced_prompt is None:
        enhanced_prompt = enhancer(services).is_enhanced
    runner = _mlx_video_runner(
        config,
        pack_dir,
        "pack_dir",
        execute_process=execute_process,
        keyframe_two_stage=pack.family == "ltx23",
        enhanced_prompt=enhanced_prompt,
        loras=loras,
    )
    return LtxCheckpointBackendGateway(runner, capabilities, pack_dir, loras)
