"""studio.toml, read once at start, with the command-line flags on top."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError as ConfigError


@dataclass(frozen=True)
class Config:
    default_backend: str
    visible_backends: tuple[str, ...]
    default_video_backend: str
    visible_video_backends: tuple[str, ...]
    sections: dict
    default_voice_backend: str = "drama3"
    visible_voice_backends: tuple[str, ...] = ("drama3", "auk_base", "auk")

    default_music_backend: str = "yue2"
    visible_music_backends: tuple[str, ...] = ("yue2",)

    require_memory_estimate: bool = False
    memory_policy: str = "immediate"
    memory_boundary_percent: int = 84
    queue_max_size: int = 0
    connect_enabled: bool = False
    connect_transport: str = "dumbpipe"
    connect_studio_port: int = 8765
    connect_dumbpipe_path: str = ""
    connect_identity_path: Path | None = None
    settings_path: Path | None = None

    def backend(self, backend_id: str) -> dict:
        """One backend's settings. Paths are absolute, and a quantize of 0 means none."""
        return dict(self.sections.get(backend_id, {}))

    def required(self, backend_id: str, key: str):
        settings = self.backend(backend_id)
        if key not in settings:
            raise ConfigError(f"studio.toml has no {key} under [{backend_id}]")
        return settings[key]


def load_config(
    path: Path,
    backend: str | None = None,
    quantize: int | None = None,
    visible: tuple[str, ...] | None = None,
    visible_video: tuple[str, ...] | None = None,
    visible_voice: tuple[str, ...] | None = None,
    memory_policy: str | None = None,
    memory_boundary_percent: int | None = None,
    queue_max_size: int | None = None,
    connect_enabled: bool | None = None,
) -> Config:
    """`backend` opens the page on that backend and makes sure the page offers it.
    `quantize` applies to the backend the page opens with. `visible` offers exactly the
    backends it names. The video and voice overrides follow the same rule. The memory and
    queue overrides are the command-line flags: a flag wins over the file. `connect_enabled`
    turns the phone connection on for this start, and never turns a file that enables it off."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    default = backend or raw["default_backend"]
    visible = visible if visible else tuple(raw.get("visible_backends", [default]))
    if default not in visible:
        visible = (default, *visible)
    default_video = raw.get("default_video_backend", "ltx25_mlx")
    visible_video = visible_video if visible_video else tuple(raw.get("visible_video_backends", [default_video]))
    if default_video not in visible_video:
        visible_video = (default_video, *visible_video)
    default_voice = raw.get("default_voice_backend", "drama3")
    visible_voice = visible_voice if visible_voice else tuple(raw.get("visible_voice_backends", [default_voice]))
    if default_voice not in visible_voice:
        visible_voice = (default_voice, *visible_voice)
    required = raw.get("require_memory_estimate", False)
    if not isinstance(required, bool):
        raise ConfigError("require_memory_estimate in studio.toml must be true or false")
    memory = raw.get("memory", {})
    if not isinstance(memory, dict):
        raise ConfigError("[memory] in studio.toml must be a table")
    policy = memory_policy if memory_policy is not None else memory.get("policy", "immediate")
    if policy not in ("immediate", "boundary"):
        raise ConfigError('memory.policy in studio.toml must be "immediate" or "boundary"')
    percent = memory_boundary_percent if memory_boundary_percent is not None else memory.get("boundary_percent", 84)
    if type(percent) is not int or not 1 <= percent <= 100:
        raise ConfigError("memory.boundary_percent in studio.toml must be a whole number from 1 to 100")
    queue = raw.get("queue", {})
    if not isinstance(queue, dict):
        raise ConfigError("[queue] in studio.toml must be a table")
    max_queue = queue_max_size if queue_max_size is not None else queue.get("max_size", 0)
    if type(max_queue) is not int or max_queue < 0:
        raise ConfigError("queue.max_size in studio.toml must be a whole number of zero or more")
    connect = raw.get("connect", {})
    if not isinstance(connect, dict):
        raise ConfigError("[connect] in studio.toml must be a table")
    enabled_in_file = connect.get("enabled", False)
    if not isinstance(enabled_in_file, bool):
        raise ConfigError("connect.enabled in studio.toml must be true or false")
    # The flag turns the connection on for one start, and never off: a settings file
    # that enables it keeps it enabled.
    if connect_enabled is not None:
        enabled_in_file = enabled_in_file or connect_enabled
    transport = connect.get("transport", "dumbpipe")
    if transport != "dumbpipe":
        raise ConfigError('connect.transport in studio.toml must be "dumbpipe"; the tailcat adapter is not built yet')
    connect_port = connect.get("studio_port", 8765)
    if type(connect_port) is not int or not 1 <= connect_port <= 65535:
        raise ConfigError("connect.studio_port in studio.toml must be a port number")
    dumbpipe_path = connect.get("dumbpipe_path", "")
    if not isinstance(dumbpipe_path, str):
        raise ConfigError("connect.dumbpipe_path in studio.toml must be a path or blank")
    identity_path = Path(connect.get("identity_path", "~/.config/open-imagine/dumbpipe-identity")).expanduser()
    if not identity_path.is_absolute():
        identity_path = (path.parent / identity_path).resolve()
    settings_path = Path(raw.get("settings_path", "~/.config/open-imagine/settings.json")).expanduser()
    settings_path = (path.parent / settings_path).resolve()
    sections = {name: _settings(value, path.parent) for name, value in raw.items() if isinstance(value, dict)}
    if quantize is not None:
        sections.setdefault(default, {})["quantize"] = quantize or None
    return Config(
        default_backend=default,
        visible_backends=visible,
        default_video_backend=default_video,
        visible_video_backends=visible_video,
        sections=sections,
        require_memory_estimate=required,
        memory_policy=policy,
        memory_boundary_percent=percent,
        queue_max_size=max_queue,
        connect_enabled=enabled_in_file,
        connect_transport=transport,
        connect_studio_port=connect_port,
        connect_dumbpipe_path=dumbpipe_path,
        connect_identity_path=identity_path,
        settings_path=settings_path,
        default_voice_backend=default_voice,
        visible_voice_backends=visible_voice,
        default_music_backend=raw.get("default_music_backend", "yue2"),
        visible_music_backends=tuple(
            dict.fromkeys((raw.get("default_music_backend", "yue2"), *raw.get("visible_music_backends", ["yue2"])))
        ),
    )


def _settings(section: dict, base: Path) -> dict:
    settings = {}
    for key, value in section.items():
        if _blank(value):
            # A blank path is a setting left empty. Resolved, it would name this file's folder.
            pass
        elif key in ("python_path", "cli_path"):
            # A venv's executable link selects the site-packages the runtime needs.
            value = str((base / Path(value).expanduser()).absolute())
        elif key.endswith(("_script", "_dir", "_path")):
            value = str((base / Path(value).expanduser()).resolve())
        if key == "quantize":
            value = value or None
        if key == "loras" and isinstance(value, list):
            # Each LoRA's file sits in a table of its own, so its path resolves here.
            value = [_lora_entry(entry, base) for entry in value]
        settings[key] = value
    return settings


def _blank(value) -> bool:
    return isinstance(value, str) and not value.strip()


def _lora_entry(entry, base: Path):
    if isinstance(entry, dict) and isinstance(entry.get("path"), str) and not _blank(entry["path"]):
        # Absolute, but not resolved: a Hugging Face cache file is a link to a blob without an
        # extension, and MLX reads the format from the extension of the name it is given.
        return {**entry, "path": os.path.abspath(base / Path(entry["path"]).expanduser())}
    return entry
