"""Filesystem and Hugging Face cache I/O for explicitly declared model assets."""

import hashlib
import json
import os
import shutil
from pathlib import Path

from studio.l1_entities.errors import InvalidJob, StudioError


class ModelAssetStorageGateway:
    def __init__(self, definitions, roots, *, scan_cache=None, protected_paths=()):
        self._definitions = definitions
        self._roots = tuple(Path(root).expanduser().resolve() for root in roots)
        self._scan_cache = scan_cache
        self._protected_paths = tuple(
            candidate
            for value in protected_paths
            for candidate in (Path(value).expanduser().absolute(), Path(value).expanduser().resolve())
        )

    def _hub(self):
        if self._scan_cache is not None:
            return self._scan_cache()
        from huggingface_hub import scan_cache_dir
        from huggingface_hub.errors import CacheNotFound

        try:
            return scan_cache_dir()
        except CacheNotFound:
            return None

    def _contains_protected(self, path):
        return any(
            protected.is_relative_to(path) or path.is_relative_to(protected) for protected in self._protected_paths
        )

    def inventory(self):
        return self._inventory()[0]

    def _inventory(self):
        assets, locations, models = {}, {}, []
        cache = self._hub()
        repos = {repo.repo_id: repo for repo in cache.repos if repo.repo_type == "model"} if cache else {}
        stamps = []
        for model_id, name, workspace, declared in self._definitions:
            models.append({"id": model_id, "name": name, "workspace": workspace})
            for asset in declared:
                key = asset.source + ":" + asset.location
                asset_id = hashlib.sha256(key.encode()).hexdigest()[:24]
                if asset_id in assets:
                    assets[asset_id]["models"].append(model_id)
                    if asset.kind == "protected" or assets[asset_id]["kind"] == "protected":
                        assets[asset_id]["blocked"] = "external"
                    elif asset.kind != assets[asset_id]["kind"]:
                        assets[asset_id]["blocked"] = "overlap"
                    continue
                blocked, size, stamp = "external" if asset.kind == "protected" else "", 0, []
                if asset.source == "hub":
                    repo = repos.get(asset.location)
                    if repo is None:
                        continue
                    if self._contains_protected(repo.repo_path):
                        blocked = "overlap"
                    size = repo.size_on_disk
                    stamp = sorted(revision.commit_hash for revision in repo.revisions)
                    locations[asset_id] = ("hub", stamp)
                else:
                    path = Path(asset.location).expanduser().absolute()
                    if not path.exists() and not path.is_symlink():
                        continue
                    if (
                        path.is_symlink()
                        or path.resolve() != path
                        or not any(path != root and path.is_relative_to(root) for root in self._roots)
                    ):
                        blocked = "external"
                    if self._contains_protected(path):
                        blocked = "overlap"
                    if blocked:
                        paths = [path]
                    elif path.is_dir():
                        paths = [
                            path,
                            *(
                                Path(parent) / name
                                for parent, dirs, files in os.walk(path, followlinks=False)
                                for name in dirs + files
                            ),
                        ]
                    else:
                        paths = [path]
                    for item in paths:
                        stat = item.lstat()
                        stamp.append((str(item.relative_to(path)), stat.st_ino, stat.st_size, stat.st_mtime_ns))
                        if not blocked and item.is_file() and not item.is_symlink() and stat.st_nlink == 1:
                            size += stat.st_size
                    stamp.sort()
                    locations[asset_id] = ("directory", path)
                assets[asset_id] = {
                    "id": asset_id,
                    "label": asset.label,
                    "location": asset.location if asset.source == "hub" else Path(asset.location).name,
                    "kind": asset.kind,
                    "source": asset.source,
                    "bytes": size,
                    "models": [model_id],
                    "blocked": blocked,
                }
                stamps.append((asset_id, stamp))
        # A configured directory must not remove a nested asset used by another model.
        for asset_id, (source, path) in locations.items():
            if source != "directory":
                continue
            for other_id, (other_source, other_path) in locations.items():
                if (
                    other_id != asset_id
                    and other_source == "directory"
                    and (path.is_relative_to(other_path) or other_path.is_relative_to(path))
                ):
                    assets[asset_id]["blocked"] = "overlap"
                    assets[asset_id]["models"] = sorted(
                        set(assets[asset_id]["models"]) | set(assets[other_id]["models"])
                    )
        revision = hashlib.sha256(
            json.dumps({"files": stamps, "assets": list(assets.values())}, sort_keys=True).encode()
        ).hexdigest()
        return {"revision": revision, "models": models, "assets": list(assets.values())}, locations

    def remove(self, asset_ids, revision):
        snapshot, locations = self._inventory()
        if snapshot["revision"] != revision:
            raise InvalidJob("Model files changed. Review the cleanup preview again.")
        by_id = {asset["id"]: asset for asset in snapshot["assets"]}
        if any(asset_id not in by_id or by_id[asset_id]["blocked"] for asset_id in asset_ids):
            raise InvalidJob("This selection contains files Studio cannot remove.")
        removed = []
        try:
            for asset_id in asset_ids:
                source, location = locations[asset_id]
                if source == "hub":
                    cache = self._hub()
                    cache.delete_revisions(*location).execute()
                elif location.is_dir():
                    shutil.rmtree(location)
                else:
                    location.unlink()
                removed.append(asset_id)
        except OSError as error:
            raise StudioError("Cleanup could not finish. Refresh model storage to see what remains.") from error
        return {"removed": removed, "bytes": sum(by_id[asset_id]["bytes"] for asset_id in removed)}
