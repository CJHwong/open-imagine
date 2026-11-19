"""The image estimate is the page's figure, so the expected numbers are the page's own.

Each figure below was worked by hand from form.js `stepSeconds` and `estimate`, with the
constants of the real qwen21 modes. A change that moves one of them moves the page's figure
too, or breaks the promise that the two agree.
"""

from dataclasses import replace

import pytest

from studio.l1_entities.capabilities import Choice, Estimate, ModeSpec, ParamSpec
from studio.l1_entities.estimate_stages import Stage
from studio.l1_entities.image_estimate import EXCLUDES, estimate_image
from studio.l3_interface_adapters.gateways.image.flux2.capabilities import flux2_capabilities
from studio.l3_interface_adapters.gateways.image.flux3.capabilities import flux3_capabilities
from studio.l3_interface_adapters.gateways.image.krea2.capabilities import krea2_capabilities
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.capabilities import minimax_h3_image_capabilities
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.capabilities import (
    minimax_h3_image_cuda_capabilities,
)
from studio.l3_interface_adapters.gateways.image.qwen21.capabilities import qwen21_capabilities
from studio.l3_interface_adapters.gateways.image.qwen21_cuda.capabilities import qwen21_cuda_capabilities
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.capabilities import qwen21_turbo_capabilities
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.capabilities import qwen_checkpoint_capabilities
from studio.l3_interface_adapters.gateways.image.viggle_turbo.capabilities import viggle_turbo_capabilities

QWEN21 = qwen21_capabilities("bf16")
GENERATE = QWEN21.mode("generate")
EDIT = QWEN21.mode("edit")
STEPS = ParamSpec(id="steps", kind="number", default=10, minimum=1, maximum=50, integer=True)


def options(mode, **raw):
    return mode.parse_options({key: str(value) for key, value in raw.items()})


def test_a_generate_figure_is_the_page_figure_for_its_size_and_count():
    estimate = estimate_image(GENERATE, options(GENERATE, size="1024x1024"), (), 2)

    assert estimate.basis == "constants"
    assert (estimate.steps, estimate.width, estimate.height, estimate.reference_count) == (40, 1024, 1024, 0)
    # 3.15 s per step at 1 MP, grown by (1.048576)^1.53, times 40 steps, and 3 s for each image.
    assert estimate.per_item_seconds == 138.5
    assert estimate.setup_seconds == 0.0
    assert estimate.total_seconds == 277.0
    assert estimate.excludes == EXCLUDES


def test_an_edit_with_a_mask_matches_the_last_picture_up_to_the_cap_and_grows_with_every_image():
    picture = (2000, 1500)
    estimate = estimate_image(EDIT, options(EDIT), (picture, picture, (64, 64)), 1, mask=True)

    # The picture's own side is 1732, so the cap of 1344 holds. The shape keeps the picture's
    # 4:3, not the mask's square. Two pictures and the mask make three images: 1 + 0.2 x 2.
    assert (estimate.width, estimate.height, estimate.reference_count) == (1552, 1164, 3)
    assert estimate.per_item_seconds == 612.4
    assert estimate.total_seconds == 612.4


def test_one_result_per_reference_carries_one_image_each():
    sizes = ((512, 512), (512, 512))
    together = estimate_image(EDIT, options(EDIT), sizes, 1)
    each = estimate_image(EDIT, options(EDIT), sizes, 2, each=True)

    assert each.reference_count == 1
    assert each.per_item_seconds is not None and together.per_item_seconds is not None
    assert each.per_item_seconds < together.per_item_seconds
    # The total rounds the exact sum, so it can differ from twice the rounded image by 0.1.
    assert (each.per_item_seconds, each.total_seconds) == (61.6, 123.1)


def test_a_mode_without_constants_or_steps_names_no_seconds():
    bare = ModeSpec(id="generate", label="Generate", params=(STEPS,))
    unmeasured = estimate_image(bare, {"steps": 10}, (), 1)
    stepless = estimate_image(replace(bare, estimate=Estimate(1.0, 1.0, 0, False)), {}, (), 1)

    assert unmeasured.basis == stepless.basis == "unavailable"
    assert unmeasured.steps == 10 and stepless.steps == 0
    assert unmeasured.total_seconds is None and unmeasured.per_item_seconds is None
    assert (unmeasured.width, unmeasured.height) == (1024, 1024)


def test_a_starting_image_skips_the_start_of_the_schedule():
    model = Estimate(1.0, 1.0, 0, False, strength_scales_steps=True)
    mode = ModeSpec(id="generate", label="Generate", params=(STEPS,), max_references=1, estimate=model)

    with_picture = estimate_image(mode, {"steps": 10, "strength": 0.35}, ((1000, 1000),), 1)
    without = estimate_image(mode, {"steps": 10, "strength": 0.35}, (), 1)
    tiny = estimate_image(mode, {"steps": 10, "strength": 0.01}, ((1000, 1000),), 1)

    assert with_picture.steps == 7  # floor(10 x 0.35) = 3 steps skipped
    assert without.steps == 10
    assert tiny.steps == 9  # one step at least


def test_the_passes_follow_the_guidance_and_the_negative():
    one = Estimate(2.0, 0.0, 0, False)
    two = replace(one, two_pass=True)

    def seconds(model, **values):
        mode = ModeSpec(id="generate", label="Generate", params=(STEPS,), estimate=model)
        return estimate_image(mode, {"steps": 1, **values}, (), 1).total_seconds

    assert seconds(one, guidance=1.0) == 2.0
    assert seconds(one, guidance=3.0) == 4.0
    assert seconds(one, cfg=3.0, negative="blurry") == 4.0
    # A mode with a negative runs the second pass only while one is set.
    assert seconds(one, cfg=3.0, negative="") == 2.0
    # A constant measured with two passes is halved for one.
    assert seconds(two) == 1.0
    assert seconds(two, guidance=4.0) == 2.0


def test_the_overhead_of_a_whole_run_is_paid_once():
    mode = ModeSpec(id="generate", label="Generate", params=(STEPS,), estimate=Estimate(1.0, 0.0, 20, False))
    estimate = estimate_image(mode, {"steps": 5}, (), 3)

    assert (estimate.per_item_seconds, estimate.setup_seconds, estimate.total_seconds) == (5.0, 20.0, 35.0)


def test_the_shape_comes_from_the_resolution_the_size_or_one_megapixel():
    mode = ModeSpec(id="edit", label="Edit", params=(STEPS,), max_references=2, estimate=Estimate(1.0, 1.0, 0, False))

    chosen = estimate_image(mode, {"steps": 1, "resolution": "512"}, ((800, 400),), 1)
    uncapped = estimate_image(mode, {"steps": 1, "resolution": "match"}, ((3000, 3000),), 1)
    unseen = estimate_image(mode, {"steps": 1, "resolution": "match"}, (), 1)
    sized = estimate_image(mode, {"steps": 1, "size": "768x512"}, (), 1)
    unsized = estimate_image(mode, {"steps": 1, "size": "auto"}, ((400, 800),), 1)

    assert (chosen.width, chosen.height) == (724, 362)  # 512^2 pixels at the reference's 2:1
    assert (uncapped.width, uncapped.height) == (3000, 3000)
    assert (unseen.width, unseen.height) == (1024, 1024)
    assert (sized.width, sized.height) == (768, 512)
    assert (unsized.width, unsized.height) == (724, 1448)


def test_exact_first_reference_match_uses_its_dimensions_for_the_estimate():
    size = ParamSpec(
        "size", "choice", "match", choices=(Choice("match", "Localized label"),), match_first_reference_dimensions=True
    )
    mode = ModeSpec(id="edit", label="Edit", params=(size, STEPS), estimate=Estimate(1.0, 1.0, 0, False))
    first, second = (1600, 900), (512, 512)

    result = estimate_image(mode, {"size": "match", "steps": 6}, (first, second), 1)

    assert (result.width, result.height) == first
    assert result.total_seconds == 8.6


def test_a_long_reference_adds_its_ratio_past_square_to_the_step_cost():
    model = Estimate(10.0, 0.0, 0, False, per_reference=1.0, per_reference_ratio=0.5)
    mode = ModeSpec(id="edit", label="Edit", params=(STEPS,), max_references=4, estimate=model)
    square, wide, tall = (2048, 2048), (3000, 1000), (1000, 2000)

    def seconds(*sizes, **kwargs):
        return estimate_image(mode, {"steps": 1}, sizes, 1, **kwargs).per_item_seconds

    assert seconds(square) == 10.0
    # 3:1 is two past square: 1 + 0.5 x 2. The long side over the short one, so 1:2 counts as 2:1.
    assert seconds(wide) == 20.0
    assert seconds(tall) == 15.0
    # Each picture adds its own: 1 + 1.0 for the second picture + 0.5 x (2 + 1).
    assert seconds(wide, tall) == 35.0
    # A run of one result each carries one picture, so it takes the mean: 1 + 0.5 x 1.5.
    assert seconds(wide, tall, each=True) == 17.5
    # The mask is not a picture: 1 + 1.0 for the mask + 0.5 x 2.
    assert seconds(wide, (64, 640), mask=True) == 30.0


def test_the_stages_split_the_total_into_the_fixed_cost_and_the_steps():
    estimate = estimate_image(GENERATE, options(GENERATE, size="1024x1024"), (), 2)

    # qwen21 pays 3 s for each image, so two images pay 6 s before their steps.
    assert [(stage.name, stage.seconds) for stage in estimate.stages] == [("fixed", 6.0), ("steps", 271.0)]


def test_a_whole_run_pays_its_fixed_stage_once():
    mode = ModeSpec(id="generate", label="Generate", params=(STEPS,), estimate=Estimate(1.0, 0.0, 20, False))

    assert [stage.seconds for stage in estimate_image(mode, {"steps": 5}, (), 3).stages] == [20.0, 15.0]


def test_the_declared_parts_of_the_overhead_are_stages_of_their_own():
    parts = (Stage("text encode", 1.5), Stage("decode", 0.5))
    mode = ModeSpec(
        id="generate", label="Generate", params=(STEPS,), estimate=Estimate(1.0, 0.0, 2.0, True, fixed_parts=parts)
    )

    stages = estimate_image(mode, {"steps": 5}, (), 3).stages

    assert stages == (Stage("text encode", 4.5), Stage("decode", 1.5), Stage("steps", 15.0))


def test_an_overhead_whose_parts_do_not_add_up_is_refused():
    with pytest.raises(ValueError, match="overhead parts add up"):
        Estimate(1.0, 0.0, 2.0, True, fixed_parts=(Stage("decode", 0.5),))


BUILT_IN = (
    qwen21_capabilities("bf16"),
    qwen21_turbo_capabilities(),
    qwen21_cuda_capabilities("bf16"),
    krea2_capabilities(),
    flux2_capabilities("int4"),
    flux3_capabilities("int4"),
    viggle_turbo_capabilities("int4"),
    minimax_h3_image_capabilities(),
    minimax_h3_image_cuda_capabilities(),
    minimax_h3_image_cuda_capabilities(badge="nvfp4"),
    qwen_checkpoint_capabilities("checkpoint", "Checkpoint", badge="bf16"),
)


@pytest.mark.parametrize("capabilities", BUILT_IN, ids=lambda capabilities: capabilities.backend_id)
@pytest.mark.parametrize("count", [1, 3])
def test_every_mode_of_every_built_in_model_splits_its_total_exactly(capabilities, count):
    """At the mode's defaults: the stages add up to the total, and the fixed stages add up
    to the overhead that the count pays."""
    for mode in capabilities.modes:
        references = ((1024, 768),) * mode.min_references
        estimate = estimate_image(mode, mode.parse_options({}), references, count)
        model = mode.reference_estimate if references and mode.reference_estimate else mode.estimate
        if estimate.total_seconds is None or model is None:
            assert estimate.stages == ()
            continue
        fixed = model.overhead * (count if model.overhead_per_image else 1)
        assert round(sum(stage.seconds for stage in estimate.stages), 1) == estimate.total_seconds
        assert round(sum(stage.seconds for stage in estimate.stages[:-1]), 1) == round(fixed, 1)
        assert estimate.stages[-1].name == "steps"
        assert estimate.stages[-1].seconds >= 0
