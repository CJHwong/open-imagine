"""Composition factory for music/yue2."""

from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.music.yue2.memory_estimate import YUE2_WEIGHT_FLOOR_GIB, estimate_peak_gib
from studio.l3_interface_adapters.gateways.music.yue2.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.music.yue2.yue2_backend_gateway import Yue2BackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild


def music_yue2_backend(config: ModelConfigurationGateway, **_):
    settings = config.backend("yue2")
    if settings.get("engine", "mlx-q8") != "mlx-q8":
        raise ModelConfigurationError("YuE2 only supports the mlx-q8 engine. Remove the old PyTorch settings.")
    script = Path(__file__).with_name("yue2_mlx_child.py")
    python = settings.get("python_path")
    command = [str(python), str(script)] if python else ["uv", "run", "--script", str(script)]
    model_dir = str(settings.get("model_dir", Path.home() / "Library/Caches/models/yue2-mlx"))
    vae_dir = str(settings.get("vae_dir", model_dir + "-vae"))
    if Path(vae_dir).resolve().is_relative_to(Path(model_dir).resolve()):
        raise ModelConfigurationError(
            "[yue2].vae_dir must be outside model_dir; converted model integrity requires a clean directory."
        )
    transcription_cache = str(
        settings.get("transcription_cache_dir", Path.home() / "Library/Caches/models/yue2-transcription")
    )
    command += ["--transcription-cache-dir", transcription_cache]
    command += ["--model-dir", model_dir, "--vae-dir", vae_dir]
    return Yue2BackendGateway(StdioChild(command), model_dir, vae_dir)


def memory_estimator(config):
    return estimate_peak_gib


PROVIDER = ModelProvider(
    "yue2",
    "music",
    music_yue2_backend,
    estimator=memory_estimator,
    storage_assets=storage_assets,
    storage_name="YuE2",
    storage_roots=("~/Library/Caches/yue2-mlx-runtime",),
    resident_gib=YUE2_WEIGHT_FLOOR_GIB,
)
