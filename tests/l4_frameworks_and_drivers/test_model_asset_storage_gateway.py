"""Cleanup touches only declared managed files and uses HF's reference-aware deletion."""

from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import InvalidJob, StudioError
from studio.l1_entities.model_asset import ModelAsset
from studio.l4_frameworks_and_drivers.model_asset_storage_gateway import ModelAssetStorageGateway


def gateway(root, assets, scan=None):
    return ModelAssetStorageGateway(assets, [root], scan_cache=scan or (lambda: None))


def definition(model, *assets):
    return (model, model.upper(), "image", assets)


def test_local_cleanup_retains_shared_files_and_detects_changes(tmp_path):
    folder = tmp_path / "weights"
    folder.mkdir()
    (folder / "part").write_bytes(b"123")
    (folder / "nested").mkdir()
    (folder / "link").symlink_to(folder / "part")
    asset = ModelAsset("Weights", str(folder))
    store = gateway(tmp_path, [definition("a", asset), definition("b", asset)])
    view = store.inventory()
    assert view == store.inventory()
    entry = view["assets"][0]
    assert entry["models"] == ["a", "b"] and entry["bytes"] == 3
    (folder / "part").write_bytes(b"changed")
    with pytest.raises(InvalidJob, match="changed"):
        store.remove((entry["id"],), view["revision"])
    view = store.inventory()
    assert store.remove((entry["id"],), view["revision"])["bytes"] == 7
    assert not folder.exists()


def test_files_hardlinks_external_symlinks_and_missing(tmp_path):
    root = tmp_path / "managed"
    root.mkdir()
    file = root / "file"
    file.write_bytes(b"1234")
    hard = root / "hard"
    hard.hardlink_to(file)
    external = tmp_path / "outside"
    external.write_text("keep")
    link = root / "link"
    link.symlink_to(external)
    store = gateway(
        root,
        [
            definition(
                "a", *(ModelAsset("Weights", str(p)) for p in (file, hard, external, link, root / "missing", root))
            )
        ],
    )
    view = store.inventory()
    assert len(view["assets"]) == 5
    assert all(asset["blocked"] for asset in view["assets"])  # root overlaps every child
    with pytest.raises(InvalidJob, match="cannot remove"):
        store.remove((view["assets"][0]["id"],), view["revision"])
    with pytest.raises(InvalidJob, match="cannot remove"):
        store.remove(("unknown",), view["revision"])
    file.unlink()
    clean = gateway(root, [definition("a", ModelAsset("Weights", str(hard)))])
    view = clean.inventory()
    assert clean.remove((view["assets"][0]["id"],), view["revision"])["bytes"] == 4
    assert external.read_text() == "keep" and link.is_symlink()


def test_overlapping_runtime_is_never_deleted_indirectly(tmp_path):
    weights = tmp_path / "model"
    runtime = weights / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "python").write_text("keep")
    store = gateway(
        tmp_path, [definition("a", ModelAsset("Weights", str(weights)), ModelAsset("Runtime", str(runtime), "runtime"))]
    )
    assert {asset["blocked"] for asset in store.inventory()["assets"]} == {"overlap"}


def test_hub_uses_sdk_deletion_and_ignores_other_repo_types(tmp_path):
    deletion = Mock()
    cache = NS(
        repos=[
            NS(
                repo_id="org/model",
                repo_type="model",
                repo_path=tmp_path / "hub",
                size_on_disk=42,
                revisions=[NS(commit_hash="abc")],
            ),
            NS(repo_id="data", repo_type="dataset"),
        ],
        delete_revisions=Mock(return_value=deletion),
    )
    store = gateway(
        tmp_path,
        [
            definition(
                "a", ModelAsset("Weights", "org/model", source="hub"), ModelAsset("Missing", "missing", source="hub")
            )
        ],
        lambda: cache,
    )
    view = store.inventory()
    assert store.remove((view["assets"][0]["id"],), view["revision"])["bytes"] == 42
    cache.delete_revisions.assert_called_once_with("abc")
    deletion.execute.assert_called_once()


def test_missing_hub_cache_and_sdk_scan(tmp_path, monkeypatch):
    import huggingface_hub
    from huggingface_hub.errors import CacheNotFound

    store = ModelAssetStorageGateway([], [tmp_path])
    monkeypatch.setattr(huggingface_hub, "scan_cache_dir", lambda: NS(repos=[]))
    assert store.inventory()["assets"] == []

    def missing():
        raise CacheNotFound("missing", tmp_path)

    monkeypatch.setattr(huggingface_hub, "scan_cache_dir", missing)
    assert store.inventory()["assets"] == []


def test_partial_io_failure_is_reported(tmp_path, monkeypatch):
    file = tmp_path / "file"
    file.write_text("keep")
    store = gateway(tmp_path, [definition("a", ModelAsset("Weights", str(file)))])
    view = store.inventory()

    def fail(self):
        raise OSError("denied")

    monkeypatch.setattr(type(file), "unlink", fail)
    with pytest.raises(StudioError, match="Refresh model storage"):
        store.remove((view["assets"][0]["id"],), view["revision"])


def test_installed_checkpoint_protects_an_identical_builtin_path(tmp_path):
    file = tmp_path / "weights"
    file.write_text("keep")
    for assets in (
        (ModelAsset("Weights", str(file)), ModelAsset("Custom", str(file), "protected")),
        (ModelAsset("Custom", str(file), "protected"), ModelAsset("Weights", str(file))),
    ):
        store = gateway(tmp_path, [definition("builtin", assets[0]), definition("installed", assets[1])])
        view = store.inventory()
        assert view["assets"][0]["blocked"] == "external"
        with pytest.raises(InvalidJob):
            store.remove((view["assets"][0]["id"],), view["revision"])


def test_external_and_symlink_roots_cannot_be_removed(tmp_path):
    managed = tmp_path / "managed"
    managed.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("keep")
    link = managed / "link"
    link.symlink_to(outside)
    store = gateway(managed, [definition("a", ModelAsset("Outside", str(outside)), ModelAsset("Link", str(link)))])
    view = store.inventory()
    assert {asset["blocked"] for asset in view["assets"]} == {"external"}
    for asset in view["assets"]:
        with pytest.raises(InvalidJob, match="cannot remove"):
            store.remove((asset["id"],), view["revision"])
    assert outside.read_text() == "keep" and link.is_symlink()


def test_a_runtime_declared_as_weights_by_another_model_is_protected(tmp_path):
    folder = tmp_path / "shared-runtime"
    folder.mkdir()
    (folder / "python").write_text("keep")
    store = gateway(
        tmp_path,
        [
            definition("a", ModelAsset("Weights", str(folder))),
            definition("b", ModelAsset("Runtime", str(folder), "runtime")),
        ],
    )
    snapshot = store.inventory()
    assert snapshot["assets"][0]["blocked"] == "overlap"
    with pytest.raises(InvalidJob):
        store.remove((snapshot["assets"][0]["id"],), snapshot["revision"])
    assert folder.exists()


def test_user_lora_inside_weights_blocks_parent_removal(tmp_path):
    folder = tmp_path / "weights"
    folder.mkdir()
    lora = folder / "user-lora.safetensors"
    lora.write_text("user file")
    store = ModelAssetStorageGateway(
        [definition("a", ModelAsset("Weights", str(folder)))],
        [tmp_path],
        scan_cache=lambda: None,
        protected_paths=[lora],
    )
    view = store.inventory()
    assert view["assets"][0]["blocked"] == "overlap"
    with pytest.raises(InvalidJob):
        store.remove((view["assets"][0]["id"],), view["revision"])
    assert lora.read_text() == "user file"


def test_user_lora_in_hub_repo_is_protected(tmp_path):
    repo = NS(
        repo_id="org/model",
        repo_type="model",
        repo_path=tmp_path / "hub",
        size_on_disk=42,
        revisions=[NS(commit_hash="abc")],
    )
    for protected, reason in ((tmp_path / "hub" / "user-lora", "overlap"), (tmp_path / "elsewhere", "")):
        store = ModelAssetStorageGateway(
            [definition("a", ModelAsset("Weights", "org/model", source="hub"))],
            [tmp_path],
            scan_cache=lambda: NS(repos=[repo]),
            protected_paths=[protected],
        )
        assert store.inventory()["assets"][0]["blocked"] == reason


def test_changed_asset_ownership_invalidates_preview_even_if_files_are_identical(tmp_path):
    file = tmp_path / "weights"
    file.write_text("weights")
    asset = ModelAsset("Weights", str(file))
    definitions = [definition("a", asset)]
    store = gateway(tmp_path, definitions)
    before = store.inventory()
    definitions.append(definition("b", asset))
    with pytest.raises(InvalidJob, match="changed"):
        store.remove((before["assets"][0]["id"],), before["revision"])
    assert file.read_text() == "weights"


def test_assets_inside_private_result_directory_cannot_be_deleted(tmp_path):
    private = tmp_path / "private-results"
    folder = private / "misconfigured-model"
    folder.mkdir(parents=True)
    result = folder / "result.enc"
    result.write_bytes(b"synthetic encrypted result")
    store = ModelAssetStorageGateway(
        [definition("a", ModelAsset("Weights", str(folder)))],
        [tmp_path],
        scan_cache=lambda: None,
        protected_paths=[private],
    )
    view = store.inventory()
    assert view["assets"][0]["blocked"] == "overlap"
    with pytest.raises(InvalidJob):
        store.remove((view["assets"][0]["id"],), view["revision"])
    assert result.read_bytes() == b"synthetic encrypted result"
