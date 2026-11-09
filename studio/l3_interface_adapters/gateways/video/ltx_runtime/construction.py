"""Construct the shared LTX process runner."""

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.boundaries.process_gateway import ProcessGateway
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import reject_lora_tables
from studio.l3_interface_adapters.gateways.video.ltx_runtime.runner import MlxVideoRunner


def _mlx_video_runner(
    config: ModelConfigurationGateway,
    model: str,
    model_key: str,
    *,
    execute_process: ProcessGateway,
    keyframe_two_stage: bool,
    enhanced_prompt=None,
    loras=None,
) -> MlxVideoRunner:
    settings = config.backend("mlx_video")
    return MlxVideoRunner(
        settings,
        model,
        True,
        keyframe_two_stage,
        model_key=model_key,
        enhanced_prompt=enhanced_prompt,
        execute_process=execute_process,
        lora_files=loras,
    )


def validate_lora_section(config: ModelConfigurationGateway, backend_id: str) -> None:
    reject_lora_tables(
        config.backend("mlx_video"), "mlx_video", f"Put LoRA tables under [{backend_id}], not [mlx_video]."
    )
