"""Pinned source identity and paths; no model engine is imported here."""

import json
from pathlib import Path

ENGINE_COMMIT = "63893b3f33a62316a8b2065bcfba69ec0cc49aff"
DEFAULT_ENGINE = "~/Library/Caches/open-imagine/engines/minimax-h3-63893b3"
DEFAULT_MODELS = "~/Library/Caches/models/minimax-h3"
MAX_RESULT_BYTES = 128 * 1024 * 1024


def model_files(root: Path) -> tuple[Path, ...]:
    return (
        root / "h3-dit-q8" / "model.safetensors.index.json",
        root / "h3-dit-q8" / "config.json",
        root / "h3-dit-q8" / "quant_config.json",
        root / "ddalcu-q8" / "text_encoder.safetensors",
        root / "ddalcu-q8" / "video_vae.safetensors",
        root / "ddalcu-q8" / "audio_vae.safetensors",
        root / "ddalcu-q8" / "tokenizer.json",
        root / "ddalcu-q8" / "tokenizer_config.json",
        root / "ddalcu-q8" / "config.json",
        root / "upstream-meta" / "FL2VA" / "text_encoder" / "config.json",
    )


def weights_ready(root: Path) -> bool:
    try:
        if any(not path.is_file() or not path.stat().st_size for path in model_files(root)):
            return False
        pack = root / "h3-dit-q8"
        quant = json.loads((pack / "quant_config.json").read_text())
        index = json.loads((pack / "model.safetensors.index.json").read_text())
        if not isinstance(quant, dict) or quant.get("bits") != 8 or quant.get("group_size") != 64:
            return False
        shards = index.get("weight_map") if isinstance(index, dict) else None
        if not isinstance(shards, dict) or not shards:
            return False
        return all(
            isinstance(name, str)
            and Path(name).name == name
            and (pack / name).is_file()
            and (pack / name).stat().st_size > 0
            for name in shards.values()
        )
    except (OSError, ValueError):
        return False
