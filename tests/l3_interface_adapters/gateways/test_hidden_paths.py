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
