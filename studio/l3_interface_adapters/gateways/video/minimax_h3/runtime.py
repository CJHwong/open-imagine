"""Pinned source identity and paths; no model engine is imported here."""

import json
from pathlib import Path

ENGINE_COMMIT = "63893b3f33a62316a8b2065bcfba69ec0cc49aff"
DEFAULT_ENGINE = "~/Library/Caches/open-imagine/engines/minimax-h3-63893b3"
DEFAULT_MODELS = "~/Library/Caches/models/minimax-h3"
MAX_RESULT_BYTES = 128 * 1024 * 1024
BASE_PACK = "h3-dit-q8"
# The converted HyperFlow H3 Flash transformer. It shares every other file with the base model.
FLASH_PACK = "h3-flash-dit-q8"


def model_files(root: Path, pack: str = BASE_PACK) -> tuple[Path, ...]:
    return (
        root / pack / "model.safetensors.index.json",
        root / pack / "config.json",
        root / pack / "quant_config.json",
        *((root / pack / "flash.json",) if pack == FLASH_PACK else ()),
        root / "ddalcu-q8" / "text_encoder.safetensors",
        root / "ddalcu-q8" / "video_vae.safetensors",
        root / "ddalcu-q8" / "audio_vae.safetensors",
        root / "ddalcu-q8" / "tokenizer.json",
        root / "ddalcu-q8" / "tokenizer_config.json",
        root / "ddalcu-q8" / "config.json",
        root / "upstream-meta" / "FL2VA" / "text_encoder" / "config.json",
    )


def weights_ready(root: Path, pack: str = BASE_PACK) -> bool:
    try:
        if any(not path.is_file() or not path.stat().st_size for path in model_files(root, pack)):
            return False
        folder = root / pack
        quant = json.loads((folder / "quant_config.json").read_text())
        index = json.loads((folder / "model.safetensors.index.json").read_text())
        if not isinstance(quant, dict) or quant.get("bits") != 8 or quant.get("group_size") != 64:
            return False
        shards = index.get("weight_map") if isinstance(index, dict) else None
        if not isinstance(shards, dict) or not shards:
            return False
        if pack == FLASH_PACK:
            flash = json.loads((folder / "flash.json").read_text())
            if not isinstance(flash, dict) or not {"hyperflow_gate", "dropped_blocks"} <= flash.keys():
                return False
        return all(
            isinstance(name, str)
            and Path(name).name == name
            and (folder / name).is_file()
            and (folder / name).stat().st_size > 0
            for name in shards.values()
        )
    except (OSError, ValueError):
        return False
