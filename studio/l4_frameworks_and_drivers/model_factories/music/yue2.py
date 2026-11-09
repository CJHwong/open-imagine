"""Composition factory for music/yue2."""

from pathlib import Path

from studio.l3_interface_adapters.gateways.music.yue2.yue2_backend_gateway import Yue2BackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l4_frameworks_and_drivers.config import Config, ConfigError


def music_yue2_backend(config: Config):
    settings = config.backend("yue2")
    if settings.get("engine", "mlx-q8") != "mlx-q8":
        raise ConfigError("YuE2 only supports the mlx-q8 engine. Remove the old PyTorch settings.")
    script = Path(__file__).resolve().parents[3] / "l3_interface_adapters/gateways/music/yue2/yue2_mlx_child.py"
    python = settings.get("python_path")
    command = [str(python), str(script)] if python else ["uv", "run", "--script", str(script)]
    model_dir = str(settings.get("model_dir", Path.home() / "Library/Caches/models/yue2-mlx"))
    vae_dir = str(settings.get("vae_dir", model_dir + "-vae"))
    if Path(vae_dir).resolve().is_relative_to(Path(model_dir).resolve()):
        raise ConfigError(
            "[yue2].vae_dir must be outside model_dir; converted model integrity requires a clean directory."
        )
    transcription_cache = str(
        settings.get("transcription_cache_dir", Path.home() / "Library/Caches/models/yue2-transcription")
    )
    command += ["--transcription-cache-dir", transcription_cache]
    command += ["--model-dir", model_dir, "--vae-dir", vae_dir]
    return Yue2BackendGateway(StdioChild(command), model_dir, vae_dir)
