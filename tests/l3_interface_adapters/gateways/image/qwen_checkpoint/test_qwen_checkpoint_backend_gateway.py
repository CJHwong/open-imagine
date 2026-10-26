"""A Qwen checkpoint that a plugin names: its folder check, its schedules and its two engines."""

from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint import qwen_checkpoint_backend_gateway as module
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.capabilities import qwen_checkpoint_capabilities
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.qwen_checkpoint_backend_gateway import (
    QwenCheckpointBackendGateway,
)
from tests.support.images import png
from tests.support.loras import lora_table

GENERATE = ImageJob("generate", "a pear", 5, {"size": "1024x1024", "steps": 12, "strength": 0.4}, ())
EDIT = ImageJob("edit", "make it night", 5, {"resolution": "match", "steps": 12}, (png(8, 8),))


EDIT_FILES = (
    "processor/preprocessor_config.json",
    "transformer/config.json",
    "vae/config.json",
    "text_encoder/config.json",
)


def checkpoint_folder(parent, name="example-checkpoint", edit=True):
    """The files mflux reads, as a converted finetune lays them out. A text-to-image export
    has no part configs, so it holds only what Generate reads."""
    folder = parent / name
    for relative in (
        "processor/tokenizer.json",
        "text_encoder/model.safetensors.index.json",
        "text_encoder/model-00001-of-00001.safetensors",
        "transformer/diffusion_pytorch_model.safetensors",
        "vae/diffusion_pytorch_model.safetensors",
        *(EDIT_FILES if edit else ()),
    ):
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_bytes(b"")
    return folder


class Recorder:
    def __init__(self, name, log):
        self.name, self.log = name, log

    def run(self, job, on_step, should_stop):
        self.log.append(f"{self.name} run")
        return ImageResult(png=b"png", width=1, height=1, seed=job.seed, steps=12)

    def prepare_batch(self, jobs, should_stop):
        self.log.append(f"{self.name} prepare")

    def release(self):
        self.log.append(f"{self.name} release")

    def load(self):
        self.log.append(f"{self.name} load")


@pytest.fixture
def log(monkeypatch):
    """The engine log, with the schedule registry and the edit patch recorded instead of run."""
    events = []
    monkeypatch.setattr(module, "register_schedules", lambda: events.append("register"))

    @contextmanager
    def edit_schedule(name):
        events.append(f"schedule {name}")
        yield
        events.append("schedule off")

    monkeypatch.setattr(module, "edit_schedule", edit_schedule)
    return events


def gateway(folder, log, loras=None, edit_scheduler="qwen_linear_quadratic", generator=None):
    return QwenCheckpointBackendGateway(
        generator or Recorder("generate", log),
        Recorder("edit", log),
        qwen_checkpoint_capabilities("example_qwen", "Example Qwen checkpoint", badge="int8"),
        str(folder),
        edit_scheduler=edit_scheduler,
        loras=loras,
    )


def test_a_generate_registers_the_schedules_and_frees_the_edit_engine_first(tmp_path, log):
    backend = gateway(checkpoint_folder(tmp_path), log)

    assert backend.run(GENERATE, None, None).png == b"png"
    assert log == ["register", "edit release", "generate run"]


def test_an_edit_samples_the_record_s_schedule_inside_the_patch(tmp_path, log):
    backend = gateway(checkpoint_folder(tmp_path), log)

    backend.run(EDIT, None, None)

    assert log == ["register", "generate release", "schedule qwen_linear_quadratic", "edit run", "schedule off"]


def test_load_starts_the_generate_engine_and_release_frees_both(tmp_path, log):
    backend = gateway(checkpoint_folder(tmp_path), log)

    backend.load()
    backend.release()

    assert log == ["generate load", "generate release", "edit release"]


def test_a_generate_batch_is_prepared_and_any_other_batch_is_left_to_the_runs(tmp_path, log):
    backend = gateway(checkpoint_folder(tmp_path), log)

    backend.prepare_batch([], None)
    backend.prepare_batch([GENERATE, EDIT], None)
    assert log == []

    backend.prepare_batch([GENERATE, GENERATE], None)
    assert log == ["register", "edit release", "generate prepare"]


def test_the_record_is_the_checkpoint_s_own_and_offers_its_loras_in_their_modes(tmp_path, log):
    backend = gateway(checkpoint_folder(tmp_path), log, loras=lora_table(tmp_path, modes=("edit",)))

    assert backend.capabilities().backend_id == "example_qwen"
    assert backend.capabilities().mode("generate").loras == ()
    assert [lora.id for lora in backend.capabilities().mode("edit").loras] == ["example_warm"]


def test_a_checkpoint_with_no_folder_setting_names_the_setting(log):
    """A blank path would reach mflux as no folder, and mflux would load the base model."""
    backend = gateway("", log)

    for call in (
        backend.load,
        lambda: backend.run(GENERATE, None, None),
        lambda: backend.prepare_batch([GENERATE], None),
    ):
        with pytest.raises(StudioError, match=r"Set model_dir under \[example_qwen\]"):
            call()
    assert log == []


def test_a_missing_folder_is_refused_before_the_engines_and_only_the_log_names_it(tmp_path, log, capsys):
    folder = tmp_path / "example-checkpoint"
    backend = gateway(folder, log)

    with pytest.raises(
        StudioError, match="weights of the example_qwen checkpoint are not complete: the folder"
    ) as refused:
        backend.run(EDIT, None, None)

    assert str(folder) not in str(refused.value)
    assert str(folder) in capsys.readouterr().err
    assert log == []


def test_an_incomplete_folder_names_each_missing_part(tmp_path, log):
    folder = checkpoint_folder(tmp_path)
    (folder / "text_encoder/model.safetensors.index.json").unlink()
    (folder / "transformer/diffusion_pytorch_model.safetensors").unlink()
    backend = gateway(folder, log)

    with pytest.raises(StudioError) as refused:
        backend.load()

    assert "text_encoder/model.safetensors.index.json, transformer/*.safetensors" in str(refused.value)


def test_a_text_to_image_export_generates_and_its_edit_is_refused_before_the_engines(tmp_path, log):
    """mflux's edit loader reads the part configs, and it would fail only after the
    generator was freed and the edit build had started."""
    backend = gateway(checkpoint_folder(tmp_path, edit=False), log)

    backend.run(GENERATE, None, None)
    with pytest.raises(StudioError) as refused:
        backend.run(EDIT, None, None)

    assert ", ".join(EDIT_FILES) in str(refused.value)
    assert log == ["register", "edit release", "generate run"]


def test_a_linked_part_counts(tmp_path, log):
    """A converted finetune links the parts it shares with the base snapshot."""
    base = checkpoint_folder(tmp_path, "base-snapshot")
    folder = tmp_path / "example-checkpoint"
    (folder / "transformer").mkdir(parents=True)
    (folder / "transformer/diffusion_pytorch_model.safetensors").write_bytes(b"")
    for part in ("processor", "text_encoder", "vae"):
        (folder / part).symlink_to(base / part)

    gateway(folder, log).load()

    assert log == ["generate load"]


def test_an_engine_error_that_quotes_the_folder_names_the_model(tmp_path, log):
    folder = checkpoint_folder(tmp_path)
    generator = Mock()
    generator.run.side_effect = StudioError(f"mflux could not read {folder}")
    backend = gateway(folder, log, generator=generator)

    with pytest.raises(StudioError) as failed:
        backend.run(GENERATE, None, None)

    assert str(failed.value) == "mflux could not read the example_qwen checkpoint"


def test_an_engine_error_that_quotes_a_file_the_folder_lacks_names_only_the_model(tmp_path, log, capsys):
    """A weight index can name a shard that is not there, and the owner names shards too."""
    folder = checkpoint_folder(tmp_path)
    shard = folder / "text_encoder/example-private-shard-00002.safetensors"
    generator = Mock()
    generator.run.side_effect = FileNotFoundError(f"No such file: {shard}")
    backend = gateway(folder, log, generator=generator)

    with pytest.raises(StudioError) as failed:
        backend.run(GENERATE, None, None)

    assert (
        str(failed.value)
        == "The run stopped on an error that names a file of the example_qwen checkpoint. The server log has the error."
    )
    assert str(shard) in capsys.readouterr().err


def test_an_engine_error_that_quotes_a_file_of_the_folder_names_the_model_and_not_the_file(tmp_path, log):
    """The owner names the weight files too, so a file name can be as private as the folder's."""
    folder = checkpoint_folder(tmp_path)
    weights = folder / "transformer/example-private-variant.safetensors"
    weights.write_bytes(b"")
    generator = Mock()
    generator.run.side_effect = StudioError(f"bad header in {weights}, and in example-private-variant.safetensors")
    backend = gateway(folder, log, generator=generator)

    with pytest.raises(StudioError) as failed:
        backend.run(GENERATE, None, None)

    assert str(failed.value) == (
        "bad header in a file of the example_qwen checkpoint, and in a file of the example_qwen checkpoint"
    )


def test_a_folder_that_cannot_be_read_is_refused_by_the_model_s_name(tmp_path, log):
    """Python 3.12 raises PermissionError from the check, and 3.14 reads the part as missing.
    Either way the message names the model, and never the folder."""
    folder = checkpoint_folder(tmp_path)
    (folder / "processor").chmod(0)
    backend = gateway(folder, log)
    try:
        with pytest.raises(StudioError) as refused:
            backend.run(GENERATE, None, None)
    finally:
        (folder / "processor").chmod(0o755)

    assert "example_qwen checkpoint" in str(refused.value)
    assert str(tmp_path) not in str(refused.value)
    assert folder.name not in str(refused.value)
    assert log == []
