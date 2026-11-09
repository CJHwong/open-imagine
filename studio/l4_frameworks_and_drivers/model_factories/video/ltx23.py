"""Composition factory for video/ltx23."""

from studio.l3_interface_adapters.gateways.video.ltx23.ltx23_backend_gateway import Ltx23BackendGateway
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.lora_table import lora_files
from studio.l4_frameworks_and_drivers.model_factories.video.ltx_runtime import _mlx_video_runner


def ltx23_mlx_backend(config: Config, enhanced_prompt=None) -> Ltx23BackendGateway:
    loras = lora_files(config, "ltx23_mlx", video=True)
    model = str(config.backend("mlx_video").get("model_ltx23", ""))
    runner = _mlx_video_runner(
        config, model, "model_ltx23", keyframe_two_stage=True, enhanced_prompt=enhanced_prompt, loras=loras
    )
    return Ltx23BackendGateway(runner, loras)
