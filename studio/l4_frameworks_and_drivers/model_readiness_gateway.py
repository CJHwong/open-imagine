"""Read each model's declared downloads on disk, and keep the record of what a prepare proved."""

import hashlib
import json
import os
import threading
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from studio.l1_entities.model_asset import ModelAsset
from studio.l1_entities.model_readiness import MISSING, READY, ModelReadiness
from studio.l2_use_cases.boundaries.model_readiness_gateway import ModelReadinessGateway

REQUIRED_KINDS = ("weights", "pack")


@dataclass(frozen=True)
class ModelBundle:
    """What one model's selection reads, and a digest of the settings that chose it.

    A changed setting, such as a precision that needs another pack, changes the digest,
    and the model needs a prepare again.
    """

    fingerprint: str
    assets: tuple[ModelAsset, ...] = ()


class FileModelReadinessGateway(ModelReadinessGateway):
    """Ready means a prepare under these settings succeeded and its declared files remain.

    A model with no bundle declares nothing to fetch, such as a plugin or the stub's fake
    engines, and is always ready. `record_path` None keeps the record in memory.
    """

    def __init__(self, bundles: Mapping[str, ModelBundle], record_path: Path | None, hub_cache: Path):
        self._bundles = dict(bundles)
        self._record_path = record_path
        self._hub_cache = hub_cache
        self._lock = threading.Lock()
        self._memory: dict[str, str] = {}

    def readiness(self, backend_id: str) -> ModelReadiness:
        bundle = self._bundles.get(backend_id)
        if bundle is None:
            return ModelReadiness(backend_id, READY)
        present, missing = 0, []
        for asset in bundle.assets:
            if asset.kind not in REQUIRED_KINDS:
                continue
            size = self._size(asset)
            if size is None:
                missing.append(asset.label)
            else:
                present += size
        recorded = self._record().get(backend_id) == bundle.fingerprint
        state = READY if recorded and not missing else MISSING
        return ModelReadiness(backend_id, state, present, tuple(missing))

    def mark_prepared(self, backend_id: str) -> None:
        bundle = self._bundles.get(backend_id)
        if bundle is None:
            return
        with self._lock:
            record = self._record()
            record[backend_id] = bundle.fingerprint
            self._write(record)

    def _record(self) -> dict[str, str]:
        if self._record_path is None:
            return dict(self._memory)
        try:
            document = json.loads(self._record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A missing or damaged record costs one more prepare per model, not a studio
            # that cannot start.
            return {}
        if not isinstance(document, dict):
            return {}
        return {key: value for key, value in document.items() if isinstance(value, str)}

    def _write(self, record: dict[str, str]) -> None:
        if self._record_path is None:
            self._memory = dict(record)
            return
        self._record_path.parent.mkdir(parents=True, exist_ok=True)
        scratch = self._record_path.with_suffix(".tmp")
        scratch.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        scratch.replace(self._record_path)

    def _size(self, asset: ModelAsset) -> int | None:
        """The bytes this asset holds on disk, or None when it is not there."""
        if asset.source == "hub":
            repository = self._hub_cache / f"models--{asset.location.replace('/', '--')}"
            snapshots = repository / "snapshots"
            if not snapshots.is_dir() or not any(snapshots.iterdir()):
                return None
            return _bytes_under(repository / "blobs")
        path = Path(asset.location).expanduser()
        if path.is_file():
            return path.stat().st_size
        if path.is_dir() and any(path.iterdir()):
            return _bytes_under(path)
        return None


WEIGHT_SETTINGS = (
    "model",
    "model_dir",
    "quantize",
    "pack_dir",
    "rewrite_model",
    "rewrite_generate_model",
    "rewrite_edit_model",
    "rewrite_precision",
)
"""The settings that choose which files a model reads. A change to one of these needs a
new prepare; a change to a default step count or a LoRA list does not."""


def model_bundles(providers, config, offered) -> dict[str, ModelBundle]:
    """One bundle for each offered built-in model: its declared downloads, and a digest of
    those and of the settings that choose its files."""
    bundles = {}
    for provider in providers:
        if provider.backend_id not in offered:
            continue
        assets = provider.storage_assets(config) if provider.storage_assets is not None else ()
        settings = config.backend(provider.backend_id)
        chosen = {key: settings[key] for key in WEIGHT_SETTINGS if key in settings}
        described = json.dumps(
            [provider.backend_id, chosen, [asdict(asset) for asset in assets]], sort_keys=True, default=str
        )
        bundles[provider.backend_id] = ModelBundle(hashlib.sha256(described.encode()).hexdigest()[:16], assets)
    return bundles


def hub_cache() -> Path:
    from huggingface_hub.constants import HF_HUB_CACHE

    return Path(HF_HUB_CACHE)


def _bytes_under(path: Path) -> int:
    total = 0
    for parent, _, files in os.walk(path):
        for name in files:
            item = Path(parent) / name
            if not item.is_symlink():
                total += item.stat().st_size
    return total
