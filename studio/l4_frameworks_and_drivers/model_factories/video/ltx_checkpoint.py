"""Composition factory for video/ltx_checkpoint."""

from studio.l3_interface_adapters.gateways.video.ltx_pack.ltx_pack_backend_gateway import LtxPackBackendGateway
from studio.l3_interface_adapters.gateways.video.shared.capabilities import ltx_pack_capabilities
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.lora_table import lora_files
from studio.l4_frameworks_and_drivers.model_factories.video.ltx_runtime import _mlx_video_runner
from studio.plugins.ltx_checkpoint_registration import LtxCheckpointRegistration


def ltx_pack_backend(config: Config, pack: LtxCheckpointRegistration, enhanced_prompt=None) -> LtxPackBackendGateway:
    """A pack that a plugin names, run by the base packs' runner, with the same enhancer.

    The folder and the LoRAs come from the plugin's own section. The engine's settings stay
    under [mlx_video]. The gateway checks the folder when a run starts, as the base packs check
    their own setting: `--all-backends` offers every installed pack, with or without a section.
    """
    pack_dir = str(config.backend(pack.backend_id).get("pack_dir", ""))
    try:
        capabilities = ltx_pack_capabilities(
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
        raise ConfigError(f"Cannot build the LTX pack {pack.backend_id}: {error}") from None
    loras = lora_files(config, pack.backend_id, video=True)
    runner = _mlx_video_runner(
        config,
        pack_dir,
        "pack_dir",
        keyframe_two_stage=pack.family == "ltx23",
        enhanced_prompt=enhanced_prompt,
        loras=loras,
    )
    return LtxPackBackendGateway(runner, capabilities, pack_dir, loras)
