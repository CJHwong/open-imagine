from studio.l1_entities.model_asset import ModelAsset
from studio.l1_entities.model_readiness import MISSING, READY, ModelReadiness
from studio.l4_frameworks_and_drivers.model_readiness_gateway import (
    STALE,
    FileModelReadinessGateway,
    model_bundles,
)


def hub_repo(cache, repository, size):
    folder = cache / f"models--{repository.replace('/', '--')}"
    (folder / "blobs").mkdir(parents=True)
    (folder / "blobs" / "abc").write_bytes(b"x" * size)
    snapshot = folder / "snapshots" / "rev"
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").symlink_to(folder / "blobs" / "abc")


def gateway(tmp_path, bundles):
    return FileModelReadinessGateway(bundles, tmp_path / "hub")


def test_a_model_that_declares_nothing_is_ready(tmp_path):
    assert gateway(tmp_path, {}).readiness("plugin") == ModelReadiness("plugin", READY)


def test_a_model_whose_files_are_all_present_is_ready_with_no_prepare(tmp_path):
    hub_repo(tmp_path / "hub", "me/model", 5)
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.json").write_text("{}")
    bundles = {
        "h3": (
            ModelAsset("Weights", "me/model", source="hub"),
            ModelAsset("Pack", str(pack), "pack"),
            ModelAsset("Runtime", str(tmp_path / "nowhere"), "runtime"),
        )
    }

    assert gateway(tmp_path, bundles).readiness("h3") == ModelReadiness("h3", READY, 7)


def test_a_missing_file_makes_the_model_missing_and_names_it(tmp_path):
    folder = tmp_path / "weights"
    folder.mkdir()
    (folder / "a").write_bytes(b"xyz")
    bundles = {"mlx": (ModelAsset("Weights", str(folder)), ModelAsset("Encoder", str(tmp_path / "e")))}

    assert gateway(tmp_path, bundles).readiness("mlx") == ModelReadiness("mlx", MISSING, 3, ("Encoder",))


def test_a_single_file_counts_its_own_size(tmp_path):
    (tmp_path / "lora.safetensors").write_bytes(b"12345")
    bundles = {"a": (ModelAsset("Adapter", str(tmp_path / "lora.safetensors")),)}

    assert gateway(tmp_path, bundles).readiness("a") == ModelReadiness("a", READY, 5)


def test_a_pack_without_its_manifest_is_missing(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "transformer.safetensors").write_bytes(b"half written")

    assert gateway(tmp_path, {"h3": (ModelAsset("Pack", str(pack), "pack"),)}).readiness("h3").missing == ("Pack",)


def test_a_link_inside_a_folder_is_not_counted_twice(tmp_path):
    folder = tmp_path / "weights"
    folder.mkdir()
    (folder / "a").write_bytes(b"xyz")
    (folder / "b").symlink_to(folder / "a")

    assert gateway(tmp_path, {"mlx": (ModelAsset("Weights", str(folder)),)}).readiness("mlx").bytes_on_disk == 3


def test_a_hub_entry_whose_blobs_link_into_a_shared_store_counts_the_linked_files(tmp_path):
    """A deduplicating cache keeps each blob once under `hub/blobs/<xx>/` and links the repo's
    blobs to it. Skipping links read Drama-3's 39 GB as 0.0 GiB on both Macs."""
    hub = tmp_path / "hub"
    hub_repo(hub, "me/model", 2)
    shared = hub / "blobs" / "7c"
    shared.mkdir(parents=True)
    (shared / "big").write_bytes(b"x" * 40)
    blob = hub / "models--me--model" / "blobs" / "def"
    blob.symlink_to(shared / "big")
    (hub / "models--me--model" / "snapshots" / "rev" / "codec.safetensors").symlink_to(blob)
    (hub / "models--me--model" / "blobs" / "broken").symlink_to(shared / "gone")

    readiness = gateway(tmp_path, {"a": (ModelAsset("Weights", "me/model", source="hub"),)}).readiness("a")

    assert readiness.bytes_on_disk == 42


def test_an_empty_folder_or_an_empty_hub_entry_is_not_present(tmp_path):
    (tmp_path / "empty").mkdir()
    (tmp_path / "hub" / "models--me--model" / "snapshots").mkdir(parents=True)
    bundles = {"a": (ModelAsset("Weights", str(tmp_path / "empty")), ModelAsset("Hub", "me/model", source="hub"))}

    assert gateway(tmp_path, bundles).readiness("a").missing == ("Weights", "Hub")


def test_a_pack_a_run_found_out_of_date_is_missing_until_a_prepare(tmp_path):
    readiness = gateway(tmp_path, {})

    readiness.mark_unprepared("h3")
    assert readiness.readiness("h3") == ModelReadiness("h3", MISSING, 0, (STALE,))

    readiness.mark_prepared("h3")
    assert readiness.readiness("h3").ready


class Config:
    def __init__(self, sections):
        self._sections = sections

    def backend(self, backend_id):
        return dict(self._sections.get(backend_id, {}))


class Provider:
    def __init__(self, backend_id, assets=None, built=None):
        self.backend_id = backend_id
        self.storage_assets = assets
        self.ready_assets = built


def test_a_bundle_holds_the_declared_downloads_and_what_a_prepare_builds():
    weights = (ModelAsset("Weights", "me/model", source="hub"),)
    pack = (ModelAsset("Pack", "/packs/me--model", "pack"),)
    providers = [
        Provider("a", lambda config: weights, lambda config: pack),
        Provider("plugin"),
        Provider("hidden", lambda config: weights),
    ]

    bundles = model_bundles(providers, Config({}), {"a", "plugin"})

    assert bundles == {"a": (*weights, *pack), "plugin": ()}
