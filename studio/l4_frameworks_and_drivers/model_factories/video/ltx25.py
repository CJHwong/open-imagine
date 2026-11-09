"""Composition factory for video/ltx25."""

from studio.l3_interface_adapters.gateways.video.ltx25.ltx25_backend_gateway import Ltx25BackendGateway
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.lora_table import lora_files
from studio.l4_frameworks_and_drivers.model_factories.video.ltx_runtime import _mlx_video_runner


def ltx25_mlx_backend(config: Config, enhanced_prompt=None) -> Ltx25BackendGateway:
    # The engine's settings are shared under [mlx_video]; each model's LoRAs are its own.
    loras = lora_files(config, "ltx25_mlx", video=True)
    model = str(config.backend("mlx_video").get("model_ltx25", ""))
    runner = _mlx_video_runner(
        config, model, "model_ltx25", keyframe_two_stage=False, enhanced_prompt=enhanced_prompt, loras=loras
    )
    return Ltx25BackendGateway(runner, loras)
