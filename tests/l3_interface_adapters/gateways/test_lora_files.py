import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.lora import Lora, LoraUse
from studio.l3_interface_adapters.gateways.image.qwen21.capabilities import qwen21_capabilities
from studio.l3_interface_adapters.gateways.lora_files import LoraFile, LoraFiles
from studio.l3_interface_adapters.gateways.video.shared.capabilities import ltx25_mlx_capabilities


def table(tmp_path, max_loras=2):
    warm = tmp_path / "warm.safetensors"
    warm.write_bytes(b"w")
    return LoraFiles(
        (
            LoraFile(Lora("example_warm", "Warm", trigger="warm light"), str(warm)),
            LoraFile(Lora("example_swap", "Swap", trigger="swap:"), str(tmp_path / "missing.safetensors"), ("edit",)),
        ),
        max_loras,
    )


def test_each_mode_offers_the_loras_that_apply_to_it(tmp_path):
    record = table(tmp_path).offer_image(qwen21_capabilities("bf16"))

    assert [lora.id for lora in record.mode("generate").loras] == ["example_warm"]
    assert [lora.id for lora in record.mode("edit").loras] == ["example_warm", "example_swap"]
    assert record.mode("edit").max_loras == 2


def test_a_mode_that_no_lora_applies_to_offers_none(tmp_path):
    only_edit = LoraFiles((LoraFile(Lora("example_swap", "Swap"), "/x", ("edit",)),), 1)

    record = only_edit.offer_image(qwen21_capabilities("bf16"))

    assert record.mode("generate").loras == () and record.mode("generate").max_loras == 0


def test_an_empty_table_leaves_the_records_as_they_were():
    assert LoraFiles().offer_image(qwen21_capabilities("bf16")) == qwen21_capabilities("bf16")
    assert LoraFiles().offer_video(ltx25_mlx_capabilities()) == ltx25_mlx_capabilities()


def test_a_video_model_offers_every_lora_in_the_table(tmp_path):
    record = table(tmp_path).offer_video(ltx25_mlx_capabilities())

    assert [lora.id for lora in record.loras] == ["example_warm", "example_swap"]
    assert record.max_loras == 2 and record.loras_with_audio is False


def test_a_lora_that_names_a_mode_the_model_lacks_is_refused():
    wrong = LoraFiles((LoraFile(Lora("example_warm", "Warm"), "/x", ("inpaint",)),), 1)

    with pytest.raises(StudioError, match="does not have: inpaint"):
        wrong.offer_image(qwen21_capabilities("bf16"))


def test_picks_become_files_and_strengths_in_the_order_picked(tmp_path):
    files = table(tmp_path)

    assert files.paths((LoraUse("example_warm", 0.7),)) == ((str(tmp_path / "warm.safetensors"), 0.7),)
    assert files.paths(()) == ()


def test_a_pick_that_has_no_file_on_disk_or_no_entry_is_refused(tmp_path):
    files = table(tmp_path)

    with pytest.raises(StudioError, match="LoRA example_swap are not on disk") as refused:
        files.paths((LoraUse("example_swap", 1.0),))
    assert "missing" not in str(refused.value)
    with pytest.raises(StudioError, match="no LoRA called example_other"):
        files.paths((LoraUse("example_other", 1.0),))


def test_trigger_words_are_listed_once_and_added_after_the_prompt(tmp_path):
    files = table(tmp_path)
    picks = (LoraUse("example_warm", 1.0), LoraUse("example_swap", 1.0), LoraUse("example_other", 1.0))

    assert files.triggers(picks) == ("warm light", "swap:")
    assert files.with_triggers("a pear", picks[:1]) == "a pear, warm light"


def test_a_table_checks_its_ids_and_its_limit():
    lora = LoraFile(Lora("example_warm", "Warm"), "/x")
    with pytest.raises(ValueError, match="twice"):
        LoraFiles((lora, lora), 2)
    with pytest.raises(ValueError, match="at least 1"):
        LoraFiles((lora,), 0)


def test_a_missing_file_s_path_goes_to_the_server_log_only(tmp_path, capsys):
    files = table(tmp_path)

    with pytest.raises(StudioError):
        files.paths((LoraUse("example_swap", 1.0),))
    assert "missing.safetensors" in capsys.readouterr().err


def test_an_error_that_names_a_lora_file_names_its_id(tmp_path):
    files = table(tmp_path)
    path = str(tmp_path / "warm.safetensors")

    assert files.hide(f"Attaching LoRA (unfused): {path}") == "Attaching LoRA (unfused): LoRA example_warm"
    assert files.hide("cannot read warm.safetensors") == "cannot read LoRA example_warm"
    # MLX quotes the path without its home folder, cut inside a folder name.
    cut = path[path.index("/", 1) + 2 :]
    assert files.hide(f"Unknown file format {cut}") == "Unknown file format LoRA example_warm"
    with pytest.raises(Cancelled, match="LoRA example_warm") as stopped, files.hidden():
        raise Cancelled(f"stopped while loading {path}")
    assert path not in str(stopped.value)
    with pytest.raises(StudioError, match="LoRA example_warm") as failed, files.hidden():
        raise RuntimeError(f"bad shape in {path}")
    assert isinstance(failed.value.__cause__, RuntimeError)


def test_an_error_that_names_no_lora_file_passes_unchanged(tmp_path):
    files = table(tmp_path)
    error = RuntimeError("out of memory")

    with pytest.raises(RuntimeError) as failed, files.hidden():
        raise error
    assert failed.value is error


def lora_in(folder, name="example-warm.safetensors"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"w")
    return LoraFiles((LoraFile(Lora("example_warm", "Warm"), str(folder / name)),), 1)


def test_a_folder_that_cannot_be_read_is_refused_by_the_lora_s_id(tmp_path):
    folder = tmp_path / "example-private-loras"
    files = lora_in(folder)
    folder.chmod(0)
    try:
        with pytest.raises(StudioError) as refused:
            files.paths((LoraUse("example_warm", 1.0),))
    finally:
        folder.chmod(0o755)

    assert "example-private-loras" not in str(refused.value)
    assert "LoRA example_warm" in str(refused.value)


def test_an_error_that_names_where_a_linked_lora_leads_names_its_id(tmp_path):
    files = lora_in(tmp_path / "example-private-loras")
    link = tmp_path / "public-warm.safetensors"
    link.symlink_to(tmp_path / "example-private-loras/example-warm.safetensors")
    linked = LoraFiles((LoraFile(Lora("example_warm", "Warm"), str(link)),), 1)

    with pytest.raises(StudioError) as failed, linked.hidden():
        raise RuntimeError(f"bad shape in {link.resolve()}")

    assert str(failed.value) == "bad shape in LoRA example_warm"
    assert files.paths((LoraUse("example_warm", 1.0),))[0][1] == 1.0
