import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l3_interface_adapters.gateways.hidden_paths import hidden, hide

FOLDER = "/Users/example/models/example-pack-q8"
NAMES = ((FOLDER, "the example_pack pack"),)


def test_a_folder_and_each_tail_of_it_are_named():
    assert hide(f"cannot open {FOLDER}/transformer.safetensors", NAMES) == (
        "cannot open the example_pack pack/transformer.safetensors"
    )
    # MLX drops the home folder, and a log line can start part of the way into a path.
    assert hide("missing models/example-pack-q8/config.json", NAMES) == "missing the example_pack pack/config.json"
    assert hide("no example-pack-q8 here", NAMES) == "no the example_pack pack here"


def test_a_name_that_holds_the_folder_s_last_part_is_not_replaced_again():
    """A folder named like its model is common: its name must survive the pass that wrote it."""
    names = (("/Users/example/models/acme", "the acme pack"),)

    assert hide("boom /Users/example/models/acme/x and models/acme", names) == "boom the acme pack/x and the acme pack"


def test_an_error_that_names_a_path_is_reworded_and_keeps_its_cause():
    with pytest.raises(Cancelled, match="the example_pack pack") as stopped, hidden(NAMES):
        raise Cancelled(f"stopped while it read {FOLDER}")
    assert FOLDER in str(stopped.value.__cause__)
    with pytest.raises(StudioError, match="the example_pack pack") as failed, hidden(NAMES):
        raise OSError(f"No such file: {FOLDER}/split_model.json")
    assert type(failed.value) is StudioError
    assert isinstance(failed.value.__cause__, OSError)


def test_an_error_that_names_no_path_passes_unchanged():
    original = RuntimeError("the engine stopped")
    with pytest.raises(RuntimeError) as failed, hidden(NAMES):
        raise original
    assert failed.value is original


def test_each_file_in_the_folder_is_named_whole_and_alone(tmp_path):
    folder = tmp_path / "example-folder"
    (folder / "transformer").mkdir(parents=True)
    (folder / "transformer/example-variant.safetensors").write_bytes(b"")
    names = ((str(folder), "the example_pack pack"),)

    assert hide(f"bad header in {folder}/transformer/example-variant.safetensors", names) == (
        "bad header in a file of the example_pack pack"
    )
    assert hide("bad header in example-variant.safetensors", names) == "bad header in a file of the example_pack pack"


def test_the_real_path_behind_a_link_is_named(tmp_path):
    """A part can link to another folder, and the engine quotes where the link leads."""
    elsewhere = tmp_path / "example-store"
    (elsewhere / "vae").mkdir(parents=True)
    (elsewhere / "vae/config.json").write_bytes(b"")
    folder = tmp_path / "example-folder"
    folder.mkdir()
    (folder / "vae").symlink_to(elsewhere / "vae")
    linked_file = tmp_path / "example-lora.safetensors"
    linked_file.symlink_to(elsewhere / "vae/config.json")
    names = ((str(folder), "the example_pack pack"), (str(linked_file), "LoRA example_warm"))

    assert hide(f"cannot parse {elsewhere}/vae/config.json", names) == "cannot parse a file of the example_pack pack"
    assert hide(f"cannot parse {elsewhere}/vae/config.json", names[1:]) == "cannot parse LoRA example_warm"


def test_a_link_back_up_the_folder_is_read_once(tmp_path):
    folder = tmp_path / "example-folder"
    (folder / "part").mkdir(parents=True)
    (folder / "part/up").symlink_to(folder)
    (folder / "part/weights.safetensors").write_bytes(b"")

    assert hide("bad weights.safetensors", ((str(folder), "the example_pack pack"),)) == (
        "bad a file of the example_pack pack"
    )


def test_past_the_file_limit_the_list_stops(tmp_path, monkeypatch):
    monkeypatch.setattr("studio.l3_interface_adapters.gateways.hidden_paths.MAX_FILES", 1)
    folder = tmp_path / "example-folder"
    folder.mkdir()
    for name in ("a.json", "b.json"):
        (folder / name).write_bytes(b"")

    text = hide("a.json and b.json", ((str(folder), "the example_pack pack"),))

    assert text.count("a file of the example_pack pack") == 1


@pytest.mark.parametrize(
    "message",
    [
        "cannot open /Volumes/example-drive/models/unlisted/weights",
        "cannot open C:\\models\\unlisted\\weights",
        "cannot open ~/models/unlisted",
        "cannot load unlisted-variant.safetensors",
        "cannot load transformer/unlisted-variant.safetensors",
        f"cannot load {FOLDER}/text_encoder/unlisted-shard-00002.safetensors",
        f"cannot open {FOLDER}/split_model.json",
    ],
)
def test_a_message_that_still_quotes_a_path_is_replaced_whole(message, capsys):
    """A path the folder walk could not list is not let through. That holds for one outside the
    folder, and for one inside it that the list lacks: a shard that a weight index names and
    the folder does not hold, or a file past the limit. The owner names those files too."""
    with pytest.raises(StudioError) as failed, hidden(NAMES):
        raise RuntimeError(message)

    assert str(failed.value) == (
        "The run stopped on an error that names a file of the example_pack pack. The server log has the error."
    )
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    "message",
    [
        "cannot fetch https://huggingface.co/Qwen/Qwen-Image-2.1/resolve/main/model.json",
        "missing text_encoder/model.safetensors.index.json",
        "missing model.safetensors.index.json",
        "step 3/12 took 4.1 s/it",
    ],
)
def test_a_url_a_relative_part_or_a_step_count_is_not_a_path(message):
    original = RuntimeError(message)
    with pytest.raises(RuntimeError) as failed, hidden(NAMES):
        raise original
    assert failed.value is original


def test_with_no_private_path_any_error_passes_unchanged():
    original = RuntimeError("cannot open /Volumes/example-drive/weights")
    with pytest.raises(RuntimeError) as failed, hidden(()):
        raise original
    assert failed.value is original


def test_a_blank_path_names_nothing():
    assert hide("an empty prompt", (("", "the example_pack pack"),)) == "an empty prompt"


def test_an_inner_block_leaves_the_last_word_to_the_outer_one(capsys):
    """A LoRA's block runs inside a pack's. The pack's folder is the outer block's to reword."""
    lora = (("/Users/example/loras/example-warm.safetensors", "LoRA example_warm"),)
    message = f"cannot open {FOLDER} and /Users/example/loras/example-warm.safetensors"

    with pytest.raises(StudioError) as reworded, hidden(NAMES), hidden(lora):
        raise RuntimeError(message)
    assert str(reworded.value) == "cannot open the example_pack pack and LoRA example_warm"

    with pytest.raises(StudioError) as replaced, hidden(NAMES), hidden(lora):
        raise RuntimeError(f"{message} and /Volumes/example-drive/unlisted/x")
    assert str(replaced.value).startswith("The run stopped on an error that names a file of the example_pack pack.")
    assert "/Volumes/example-drive/unlisted/x" in capsys.readouterr().err


def test_a_file_past_the_limit_is_not_let_through(tmp_path, monkeypatch):
    monkeypatch.setattr("studio.l3_interface_adapters.gateways.hidden_paths.MAX_FILES", 1)
    folder = tmp_path / "example-folder"
    (folder / "transformer").mkdir(parents=True)
    for name in ("a.json", "example-private-variant.safetensors"):
        (folder / "transformer" / name).write_bytes(b"")
    names = ((str(folder), "the example_pack pack"),)

    with pytest.raises(StudioError) as failed, hidden(names):
        raise RuntimeError(f"bad header in {folder}/transformer/example-private-variant.safetensors")

    assert "example-private-variant" not in str(failed.value)
    assert str(failed.value).startswith("The run stopped on an error that names a file of the example_pack pack.")
