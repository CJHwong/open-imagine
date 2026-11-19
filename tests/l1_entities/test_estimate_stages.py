"""The stages of an estimate, and the load that a cold model adds."""

import pytest

from studio.l1_entities.estimate_stages import Stage, check_parts, split, with_residency
from studio.l1_entities.image_estimate import EXCLUDES, ImageEstimate


def total(stages):
    return round(sum(stage.seconds for stage in stages), 1)


def test_a_figure_without_declared_parts_has_a_fixed_stage_and_a_computed_one():
    assert split((), 1.24, 1.2, "steps", 9.7) == (Stage("fixed", 1.2), Stage("steps", 8.5))


def test_declared_parts_scale_to_the_rounded_fixed_figure_and_the_largest_takes_the_rest():
    parts = (Stage("encode", 3.0), Stage("decode", 1.0), Stage("vae", 0.5))

    stages = split(parts, 4.5, 10.0, "generation", 40.0)

    assert [stage.name for stage in stages] == ["encode", "decode", "vae", "generation"]
    assert stages[1:] == (Stage("decode", 2.2), Stage("vae", 1.1), Stage("generation", 30.0))
    assert stages[0] == Stage("encode", 6.7)
    assert total(stages) == 40.0


@pytest.mark.parametrize("fixed", [0.3, 1.0, 2.25, 7.77, 33.333])
@pytest.mark.parametrize("computed", [0.0, 0.04, 5.55, 100.0])
def test_the_stages_add_up_to_the_total_and_none_is_negative(fixed, computed):
    parts = (Stage("a", fixed * 0.6), Stage("b", fixed * 0.3), Stage("c", fixed * 0.1))
    figure = round(fixed + computed, 1)

    stages = split(parts, fixed, round(fixed, 1), "steps", figure)

    assert total(stages) == figure
    assert all(stage.seconds >= 0 for stage in stages)


def test_a_zero_fixed_part_is_a_zero_stage():
    assert split((), 0.0, 0.0, "generation", 6.1) == (Stage("fixed", 0.0), Stage("generation", 6.1))


def test_declared_parts_must_add_up_to_the_cost_they_split():
    check_parts((), 4.0, "The overhead")
    check_parts((Stage("a", 3.0), Stage("b", 1.04)), 4.0, "The overhead")
    with pytest.raises(ValueError, match=r"The overhead parts add up to 3\.5 s, not the 4 s they split"):
        check_parts((Stage("a", 3.0), Stage("b", 0.5)), 4.0, "The overhead")


def figure(**fields):
    return ImageEstimate("constants", 4, 512, 512, 0, 2.0, 1.0, 9.0, **fields)


def test_a_cold_model_adds_its_declared_load_and_drops_it_from_the_excludes():
    cold = with_residency(figure(load_seconds=20.0), False)

    assert (cold.resident, cold.with_load_seconds, cold.total_seconds) == (False, 29.0, 9.0)
    assert cold.excludes == ("weight download", "queue wait")


def test_a_held_model_adds_nothing_and_keeps_the_excludes():
    warm = with_residency(figure(load_seconds=20.0), True)

    assert (warm.resident, warm.with_load_seconds, warm.excludes) == (True, 9.0, EXCLUDES)


def test_a_cold_model_with_no_declared_load_has_no_figure_with_the_load():
    cold = with_residency(figure(), False)

    assert (cold.with_load_seconds, cold.excludes) == (None, EXCLUDES)


def test_a_figure_that_holds_its_load_adds_nothing_even_when_cold():
    clip = with_residency(figure(load_seconds=20.0, excludes=("queue wait",)), False)

    assert (clip.with_load_seconds, clip.excludes) == (9.0, ("queue wait",))


def test_no_figure_or_no_residency_gives_no_figure_with_the_load():
    assert (
        with_residency(ImageEstimate("unavailable", 0, 512, 512, 0, load_seconds=5.0), False).with_load_seconds is None
    )
    unknown = with_residency(figure(load_seconds=20.0), None)
    assert (unknown.resident, unknown.with_load_seconds, unknown.excludes) == (None, None, EXCLUDES)
