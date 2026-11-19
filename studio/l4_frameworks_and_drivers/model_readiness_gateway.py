"""Read each model's declared files on disk to tell whether it can run without a download."""

import os
import threading
from collections.abc import Mapping
from pathlib import Path

from studio.l1_entities.model_asset import ModelAsset
from studio.l1_entities.model_readiness import MISSING, READY, ModelReadiness
from studio.l2_use_cases.boundaries.model_readiness_gateway import ModelReadinessGateway

REQUIRED_KINDS = ("weights", "pack")
PACK_MANIFEST = "pack.json"
STALE = "Pack for this build"
"""The label a model carries while a run has found its pack out of date."""


class FileModelReadinessGateway(ModelReadinessGateway):
    """Ready means every declared file of the model is on disk.

    A model that declares nothing, such as a plugin or the stub's fake engines, is ready.
    A pack is present when its directory holds a `pack.json`. A pack can be present and
    still out of date for this machine's torch build, which only its engine can tell; a
    run that finds that marks the model, in memory, until a prepare succeeds.
    """

    def __init__(self, bundles: Mapping[str, tuple[ModelAsset, ...]], hub_cache: Path):
        self._bundles = dict(bundles)
        self._hub_cache = hub_cache
        self._lock = threading.Lock()
        self._stale: set[str] = set()

    def readiness(self, backend_id: str) -> ModelReadiness:
        present, missing = 0, []
        for asset in self._bundles.get(backend_id, ()):
            if asset.kind not in REQUIRED_KINDS:
                continue
            size = self._size(asset)
            if size is None:
                missing.append(asset.label)
            else:
                present += size
        with self._lock:
            if backend_id in self._stale:
                missing.append(STALE)
        return ModelReadiness(backend_id, MISSING if missing else READY, present, tuple(missing))

    def mark_prepared(self, backend_id: str) -> None:
        with self._lock:
            self._stale.discard(backend_id)

    def mark_unprepared(self, backend_id: str) -> None:
        with self._lock:
            self._stale.add(backend_id)

    def _size(self, asset: ModelAsset) -> int | None:
        """The bytes this asset holds on disk, or None when it is not there."""
        if asset.source == "hub":
            repository = self._hub_cache / f"models--{asset.location.replace('/', '--')}"
            snapshots = repository / "snapshots"
            if not snapshots.is_dir() or not any(snapshots.iterdir()):
                return None
            return _bytes_under(repository / "blobs")
        path = Path(asset.location).expanduser()
        if asset.kind == "pack":
            return _bytes_under(path) if (path / PACK_MANIFEST).is_file() else None
        if path.is_file():
            return path.stat().st_size
        if path.is_dir() and any(path.iterdir()):
            return _bytes_under(path)
        return None


def model_bundles(providers, config, offered) -> dict[str, tuple[ModelAsset, ...]]:
    """The files each offered built-in model reads: its declared downloads, and the files a
    prepare builds that a run then reads, such as a pack of quantized weights."""
    bundles = {}
    for provider in providers:
        if provider.backend_id not in offered:
            continue
        declared = provider.storage_assets(config) if provider.storage_assets is not None else ()
        built = provider.ready_assets(config) if provider.ready_assets is not None else ()
        bundles[provider.backend_id] = (*declared, *built)
    return bundles


def hub_cache() -> Path:
    from huggingface_hub.constants import HF_HUB_CACHE

    return Path(HF_HUB_CACHE)


def _bytes_under(path: Path) -> int:
    """The bytes of every file under `path`, each real file once. A link counts the file it
    points to, because a deduplicating hub cache links each repo's blobs into a shared store,
    and a link that points nowhere counts nothing."""
    seen = set()
    for parent, _, files in os.walk(path):
        for name in files:
            target = (Path(parent) / name).resolve()
            if target.is_file():
                seen.add(target)
    return sum(target.stat().st_size for target in seen)
