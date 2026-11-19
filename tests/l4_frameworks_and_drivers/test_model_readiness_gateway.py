import json

from studio.l1_entities.model_asset import ModelAsset
from studio.l1_entities.model_readiness import MISSING, READY, ModelReadiness
from studio.l4_frameworks_and_drivers.model_readiness_gateway import (
    FileModelReadinessGateway,
    ModelBundle,
    model_bundles,
)


def hub_repo(cache, repository, size):
    folder = cache / f"models--{repository.replace('/', '--')}"
    (folder / "blobs").mkdir(parents=True)
    (folder / "blobs" / "abc").write_bytes(b"x" * size)
    snapshot = folder / "snapshots" / "rev"
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").symlink_to(folder / "blobs" / "abc")


def gateway(tmp_path, bundles, record=True):
    return FileModelReadinessGateway(bundles, tmp_path / "prepared.json" if record else None, tmp_path / "hub")


def test_a_model_with_no_bundle_is_always_ready(tmp_path):
    assert gateway(tmp_path, {}).readiness("plugin") == ModelReadiness("plugin", READY)


def test_a_model_never_prepared_is_missing_even_with_its_files_present(tmp_path):
    hub_repo(tmp_path / "hub", "me/model", 5)
    bundles = {"qwen": ModelBundle("f1", (ModelAsset("Weights", "me/model", source="hub"),))}

    assert gateway(tmp_path, bundles).readiness("qwen") == ModelReadiness("qwen", MISSING, 5)


def test_a_prepared_model_with_its_files_present_is_ready_and_counts_its_bytes(tmp_path):
    hub_repo(tmp_path / "hub", "me/model", 5)
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.json").write_text("{}")
    bundles = {
        "qwen": ModelBundle(
            "f1",
            (
                ModelAsset("Weights", "me/model", source="hub"),
                ModelAsset("Pack", str(pack / "pack.json"), "pack"),
                ModelAsset("Runtime", str(tmp_path / "nowhere"), "runtime"),
            ),
        )
    }
    readiness = gateway(tmp_path, bundles)

    readiness.mark_prepared("qwen")

    assert readiness.readiness("qwen") == ModelReadiness("qwen", READY, 7)


def test_a_file_removed_after_the_prepare_makes_the_model_missing_again(tmp_path):
    folder = tmp_path / "weights"
    folder.mkdir()
    (folder / "a").write_bytes(b"xyz")
    bundles = {
        "mlx": ModelBundle("f1", (ModelAsset("Weights", str(folder)), ModelAsset("Encoder", str(tmp_path / "e"))))
    }
    readiness = gateway(tmp_path, bundles)
    readiness.mark_prepared("mlx")

    assert readiness.readiness("mlx") == ModelReadiness("mlx", MISSING, 3, ("Encoder",))


def test_a_link_inside_a_folder_is_not_counted_twice(tmp_path):
    folder = tmp_path / "weights"
    folder.mkdir()
    (folder / "a").write_bytes(b"xyz")
    (folder / "b").symlink_to(folder / "a")
    readiness = gateway(tmp_path, {"mlx": ModelBundle("f1", (ModelAsset("Weights", str(folder)),))})

    assert readiness.readiness("mlx").bytes_on_disk == 3


def test_an_empty_folder_or_an_empty_hub_entry_is_not_present(tmp_path):
    (tmp_path / "empty").mkdir()
    (tmp_path / "hub" / "models--me--model" / "snapshots").mkdir(parents=True)
    bundles = {
        "a": ModelBundle(
            "f1", (ModelAsset("Weights", str(tmp_path / "empty")), ModelAsset("Hub", "me/model", source="hub"))
        )
    }
    readiness = gateway(tmp_path, bundles)
    readiness.mark_prepared("a")

    assert readiness.readiness("a").missing == ("Weights", "Hub")


def test_changed_settings_need_another_prepare(tmp_path):
    first = gateway(tmp_path, {"a": ModelBundle("fp8")})
    first.mark_prepared("a")

    assert gateway(tmp_path, {"a": ModelBundle("fp8")}).readiness("a").ready
    assert not gateway(tmp_path, {"a": ModelBundle("nvfp4")}).readiness("a").ready


def test_the_record_keeps_the_other_models_and_survives_a_restart(tmp_path):
    bundles = {"a": ModelBundle("f1"), "b": ModelBundle("f2")}
    gateway(tmp_path, bundles).mark_prepared("a")
    gateway(tmp_path, bundles).mark_prepared("b")

    assert json.loads((tmp_path / "prepared.json").read_text()) == {"a": "f1", "b": "f2"}


def test_marking_a_model_with_no_bundle_writes_nothing(tmp_path):
    gateway(tmp_path, {}).mark_prepared("plugin")

    assert not (tmp_path / "prepared.json").exists()


def test_a_damaged_record_reads_as_nothing_prepared(tmp_path):
    bundles = {"a": ModelBundle("f1")}
    (tmp_path / "prepared.json").write_text("{not json")
    assert not gateway(tmp_path, bundles).readiness("a").ready

    (tmp_path / "prepared.json").write_text('["a"]')
    assert not gateway(tmp_path, bundles).readiness("a").ready

    (tmp_path / "prepared.json").write_text('{"a": 1}')
    assert not gateway(tmp_path, bundles).readiness("a").ready


def test_a_record_in_memory_lasts_as_long_as_the_gateway(tmp_path):
    readiness = gateway(tmp_path, {"a": ModelBundle("f1")}, record=False)

    readiness.mark_prepared("a")

    assert readiness.readiness("a").ready
    assert not (tmp_path / "prepared.json").exists()


class Config:
    def __init__(self, sections):
        self._sections = sections

    def backend(self, backend_id):
        return dict(self._sections.get(backend_id, {}))


class Provider:
    def __init__(self, backend_id, assets=None):
        self.backend_id = backend_id
        self.storage_assets = assets


def test_a_bundle_changes_with_a_weight_setting_and_not_with_a_run_default():
    weights = (ModelAsset("Weights", "me/model", source="hub"),)
    providers = [Provider("a", lambda config: weights), Provider("plugin"), Provider("hidden")]

    def bundles(section):
        return model_bundles(providers, Config({"a": section}), {"a", "plugin"})

    first = bundles({"quantize": "fp8", "steps": 8})

    assert set(first) == {"a", "plugin"}
    assert first["a"].assets == weights
    assert first["plugin"].assets == ()
    assert bundles({"quantize": "fp8", "steps": 20})["a"] == first["a"]
    assert bundles({"quantize": "nvfp4", "steps": 8})["a"].fingerprint != first["a"].fingerprint
