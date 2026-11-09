"""Construct the shared LTX process runner."""

from studio.l3_interface_adapters.gateways.video.ltx_runtime.runner import MlxVideoRunner
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner


def _mlx_video_runner(
    config: Config, model: str, model_key: str, *, keyframe_two_stage: bool, enhanced_prompt=None, loras=None
) -> MlxVideoRunner:
    settings = config.backend("mlx_video")
    return MlxVideoRunner(
        settings,
        model,
        True,
        keyframe_two_stage,
        model_key=model_key,
        enhanced_prompt=enhanced_prompt,
        execute_process=SubprocessRunner().execute,
        lora_files=loras,
    )
