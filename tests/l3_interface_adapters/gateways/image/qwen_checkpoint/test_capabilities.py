"""What a Qwen checkpoint record offers the page, and the values it refuses."""

import pytest

from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.capabilities import qwen_checkpoint_capabilities


def record(**fields):
    return qwen_checkpoint_capabilities("example_qwen", "Example Qwen checkpoint", badge="int8", **fields)


def test_the_defaults_give_both_modes_at_cfg_1_with_no_aids_and_no_estimate():
    capabilities = record()
    generate, edit = capabilities.modes

    assert (capabilities.backend_id, capabilities.name, capabilities.badge) == (
        "example_qwen",
        "Example Qwen checkpoint",
        "int8",
    )
    assert capabilities.description == "A Qwen-Image-2.1 checkpoint on the studio's mflux engine."
    assert [param.id for param in generate.params] == ["size", "steps", "strength"]
    assert [param.id for param in edit.params] == ["resolution", "steps"]
    for mode in (generate, edit):
        assert (mode.looks, mode.templates, mode.estimate, mode.region_marking) == ((), (), None, False)
    assert generate.max_references == 1
    assert (edit.min_references, edit.max_references, edit.each_reference) == (1, 10, True)
    assert generate.params[0].default == "1024x1024"
    assert edit.params[0].default == "match"
    assert (generate.params[1].default, generate.params[1].minimum, generate.params[1].maximum) == (40, 1, 100)
    assert (edit.params[1].default, edit.params[1].minimum, edit.params[1].maximum) == (40, 2, 100)


def test_an_edit_never_offers_one_step_which_mflux_refuses_after_the_build():
    generate, edit = record(steps=(1, 1, 1)).modes

    assert (generate.params[1].default, generate.params[1].minimum, generate.params[1].maximum) == (1, 1, 1)
    assert (edit.params[1].default, edit.params[1].minimum, edit.params[1].maximum) == (2, 2, 2)


@pytest.mark.parametrize("sampler", ["euler", "euler_ancestral"])
def test_linear_quadratic_keeps_the_generate_reference_and_its_strength(sampler):
    """The page has no Generate without a reference slot, so the slot stays on every schedule."""
    generate, _ = record(scheduler="linear_quadratic", generate_sampler=sampler).modes

    assert [param.id for param in generate.params] == ["size", "steps", "strength"]
    assert generate.max_references == 1


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"scheduler": "karras"}, "scheduler is linear or linear_quadratic, not 'karras'"),
        ({"generate_sampler": "heun"}, "generate_sampler is euler or euler_ancestral, not 'heun'"),
        ({"generate_sampler": "euler_ancestral"}, "euler_ancestral needs scheduler linear_quadratic"),
        ({"steps": (12, 13, 40)}, r"1 <= minimum <= default <= maximum, not \(12, 13, 40\)"),
        ({"steps": (12, 8, 10)}, "minimum <= default <= maximum"),
        ({"steps": (1, 0, 4)}, "minimum <= default <= maximum"),
        ({"generate_size": "1000x1000"}, "'1000x1000' is not one of the Qwen sizes"),
        ({"generate_size": "match"}, "'match' is not one of the Qwen sizes"),
        ({"max_edit_references": 0}, "max_edit_references is 1 to 10, not 0"),
        ({"max_edit_references": 11}, "max_edit_references is 1 to 10, not 11"),
    ],
)
def test_a_value_the_engine_cannot_run_names_its_field(fields, message):
    with pytest.raises(ValueError, match=message):
        record(**fields)


def test_ancestral_runs_on_linear_quadratic():
    assert record(scheduler="linear_quadratic", generate_sampler="euler_ancestral").backend_id == "example_qwen"
