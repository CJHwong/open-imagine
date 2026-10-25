"""The LoRAs a built-in backend offers, read from its section of studio.toml.

    [qwen21_turbo]
    max_loras = 3

    [[qwen21_turbo.loras]]
    id = "warm_film"
    label = "Warm film"
    path = "~/loras/warm-film.safetensors"
    strength = 0.8
    recommended = [0.6, 1.0]
    trigger = "warm film"
    modes = ["generate"]

The file is not checked here. Every backend is built at start, the stub included, so
a check here would stop page work on a machine that never runs the model. A run checks
it, and refuses a missing file by its id.
"""

from studio.l1_entities.lora import Lora
from studio.l3_interface_adapters.gateways.lora_files import LoraFile, LoraFiles
from studio.l4_frameworks_and_drivers.config import Config, ConfigError

KEYS = {
    "id",
    "label",
    "path",
    "strength",
    "min_strength",
    "max_strength",
    "strength_step",
    "recommended",
    "trigger",
    "hint",
    "modes",
}
NUMBERS = ("strength", "min_strength", "max_strength", "strength_step")


def lora_files(config: Config, backend_id: str, video: bool = False) -> LoraFiles:
    """`video` refuses `modes`: a video model applies one LoRA set to every mode."""
    if video:
        # The LTX engine's own settings live here, so a table here is an easy slip.
        no_loras(config, "mlx_video", f"Put LoRA tables under [{backend_id}], not [mlx_video].")
    settings = config.backend(backend_id)
    entries = settings.get("loras", [])
    if not isinstance(entries, list):
        raise ConfigError(f"loras under [{backend_id}] must be a list of [[{backend_id}.loras]] tables")
    files = tuple(_file(entry, backend_id, video) for entry in entries)
    # One LoRA at a time unless the section says more: each one adds work to every step.
    max_loras = settings.get("max_loras", 1 if files else 0)
    if isinstance(max_loras, bool) or not isinstance(max_loras, int):
        raise ConfigError(f"max_loras under [{backend_id}] must be a whole number")
    try:
        return LoraFiles(files, max_loras)
    except ValueError as error:
        raise ConfigError(f"[{backend_id}]: {error}") from None


def no_loras(config: Config, backend_id: str, advice: str = "") -> None:
    """A section whose engine takes no LoRAs refuses a table, rather than ignore it."""
    if config.backend(backend_id).get("loras"):
        advice = advice or f"Remove its [[{backend_id}.loras]] tables."
        raise ConfigError(f"[{backend_id}] takes no LoRAs. {advice}")


def _file(entry, backend_id: str, video: bool) -> LoraFile:
    where = f"[[{backend_id}.loras]]"
    if not isinstance(entry, dict):
        raise ConfigError(f"Each {where} entry must be a table")
    unknown = sorted(set(entry) - KEYS)
    if unknown:
        raise ConfigError(f"{where} has keys it does not know: {', '.join(unknown)}")
    missing = [key for key in ("id", "label", "path") if not isinstance(entry.get(key), str) or not entry[key].strip()]
    if missing:
        raise ConfigError(f"{where} needs {', '.join(missing)}")
    numbers = {key: entry[key] for key in NUMBERS if key in entry}
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers.values()):
        raise ConfigError(f"{where} {entry['id']}: {', '.join(numbers)} must be numbers")
    recommended = entry.get("recommended")
    if recommended is not None and (
        not isinstance(recommended, list)
        or len(recommended) != 2
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in recommended)
    ):
        raise ConfigError(f"{where} {entry['id']}: recommended must be two numbers, low then high")
    if video and "modes" in entry:
        raise ConfigError(f"{where} {entry['id']}: a video LoRA applies to every mode, so remove modes")
    modes = entry.get("modes", [])
    if not isinstance(modes, list) or any(not isinstance(mode, str) for mode in modes):
        raise ConfigError(f"{where} {entry['id']}: modes must be a list of mode ids")
    for key in ("trigger", "hint"):
        if not isinstance(entry.get(key, ""), str):
            raise ConfigError(f"{where} {entry['id']}: {key} must be text")
    try:
        lora = Lora(
            id=entry["id"],
            label=entry["label"],
            **{key: float(value) for key, value in numbers.items()},
            recommended=(float(recommended[0]), float(recommended[1])) if recommended else None,
            trigger=entry.get("trigger", ""),
            hint=entry.get("hint", ""),
        )
    except ValueError as error:
        raise ConfigError(f"{where}: {error}") from None
    return LoraFile(lora, entry["path"], tuple(modes))
