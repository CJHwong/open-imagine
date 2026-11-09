"""Parse Studio LoRA table structure under an explicitly supplied provider policy.

This reads resolved mappings, not configuration files or LoRA tensors. Passing
this parser does not establish that an engine can load a weight file. The model
runtime checks file format, tensor names, shapes and compatibility before a run.
"""

from collections.abc import Mapping

from studio.l1_entities.lora import Lora
from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.lora_files import LoraFile, LoraFiles
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import OPTION_FIELDS, LoraTablePolicy

KEYS = {"id", "label", "path", "modes"} | OPTION_FIELDS
NUMBERS = ("strength", "min_strength", "max_strength", "strength_step")


def parse_lora_tables(settings: Mapping, backend_id: str, *, policy: LoraTablePolicy) -> LoraFiles:
    """Validate only the common host schema and the options this provider accepts."""
    entries = settings.get("loras", [])
    if not isinstance(entries, list):
        raise ModelConfigurationError(f"loras under [{backend_id}] must be a list of [[{backend_id}.loras]] tables")
    files = tuple(_file(entry, backend_id, policy) for entry in entries)
    # One LoRA at a time unless the section says more: each one adds work to every step.
    max_loras = settings.get("max_loras", 1 if files else 0)
    if isinstance(max_loras, bool) or not isinstance(max_loras, int):
        raise ModelConfigurationError(f"max_loras under [{backend_id}] must be a whole number")
    try:
        return LoraFiles(files, max_loras)
    except ValueError as error:
        raise ModelConfigurationError(f"[{backend_id}]: {error}") from None


def reject_lora_tables(settings: Mapping, backend_id: str, advice: str = "") -> None:
    """A section whose engine takes no LoRAs refuses a table, rather than ignore it."""
    if settings.get("loras"):
        advice = advice or f"Remove its [[{backend_id}.loras]] tables."
        raise ModelConfigurationError(f"[{backend_id}] takes no LoRAs. {advice}")


def _file(entry, backend_id: str, policy: LoraTablePolicy) -> LoraFile:
    where = f"[[{backend_id}.loras]]"
    if not isinstance(entry, dict):
        raise ModelConfigurationError(f"Each {where} entry must be a table")
    unknown = sorted(set(entry) - KEYS)
    if unknown:
        raise ModelConfigurationError(f"{where} has keys it does not know: {', '.join(unknown)}")
    unsupported = sorted((set(entry) - {"id", "label", "path", "modes"}) - policy.supported_options)
    if unsupported:
        raise ModelConfigurationError(f"{where}: this model does not support {', '.join(unsupported)}")
    missing = [key for key in ("id", "label", "path") if not isinstance(entry.get(key), str) or not entry[key].strip()]
    if missing:
        raise ModelConfigurationError(f"{where} needs {', '.join(missing)}")
    numbers = {key: entry[key] for key in NUMBERS if key in entry}
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers.values()):
        raise ModelConfigurationError(f"{where} {entry['id']}: {', '.join(numbers)} must be numbers")
    recommended = entry.get("recommended")
    if recommended is not None and (
        not isinstance(recommended, list)
        or len(recommended) != 2
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in recommended)
    ):
        raise ModelConfigurationError(f"{where} {entry['id']}: recommended must be two numbers, low then high")
    if not policy.mode_scoped and "modes" in entry:
        raise ModelConfigurationError(
            f"{where} {entry['id']}: a LoRA for this model applies to every mode, so remove modes"
        )
    modes = entry.get("modes", [])
    if not isinstance(modes, list) or any(not isinstance(mode, str) for mode in modes):
        raise ModelConfigurationError(f"{where} {entry['id']}: modes must be a list of mode ids")
    for key in ("trigger", "hint"):
        if not isinstance(entry.get(key, ""), str):
            raise ModelConfigurationError(f"{where} {entry['id']}: {key} must be text")
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
        raise ModelConfigurationError(f"{where}: {error}") from None
    return LoraFile(lora, entry["path"], tuple(modes))
