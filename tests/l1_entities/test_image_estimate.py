"""The image estimate is the page's figure, so the expected numbers are the page's own.

Each figure below was worked by hand from form.js `stepSeconds` and `estimate`, with the
constants of the real qwen21 modes. A change that moves one of them moves the page's figure
too, or breaks the promise that the two agree.
"""

from dataclasses import replace

from studio.l1_entities.capabilities import Estimate, ModeSpec, ParamSpec
from studio.l1_entities.image_estimate import EXCLUDES, estimate_image
from studio.l3_interface_adapters.gateways.image.qwen21.capabilities import qwen21_capabilities

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
