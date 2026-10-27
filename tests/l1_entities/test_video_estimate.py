"""The time of a clip, from the model's constants and the clip's settings.

The constants here are round numbers, so each figure can be worked by hand. The real
constants and the runs behind them are in the video gateway's capabilities.
"""

from dataclasses import replace

import pytest

from studio.l1_entities.video_capabilities import VideoAdapter, VideoEstimate
from studio.l1_entities.video_estimate import FAST_MODE, estimate_clip, run_seconds, tokens

# The fit gives 10 s for any clip, which the runner scales to 30 s. The loads and the prompt
# pass add 60 s, and 20 s of that is the prompt pass.
FLAT = VideoEstimate(
    load=(10.0, 0.0),
    stage_1=(0.0, 0.0),
    stage_2=(0.0, 0.0),
    decode=(0.0, 0.0),
    scale=2.0,
    pack_factor=1.5,
    fixed_seconds=60.0,
    enhance_seconds=20.0,
    lora_seconds=10.0,
    guided_factor=2.0,
    guided_with_references=True,
    edit=(5.0, 100.0),
    excludes=("weight download",),
)
EFFECT = VideoAdapter(id="deblur", label="Deblur", hint="", mode="edit", file="deblur.safetensors")


def test_a_clip_counts_its_latent_tokens_in_thousands():
    # 121 frames make 16 latent frames, and 960 x 544 makes 30 x 17 tokens in each.
    assert tokens(960, 544, 121) == 8.16
    assert tokens(256, 256, 9) == 0.128


def test_the_fit_adds_the_loads_both_stages_and_the_decode():
    model = VideoEstimate(load=(2.0, 1.0), stage_1=(1.0, 0.5), stage_2=(1.0, 0.1), decode=(-10.0, 1.0))

    # Load 2 + 8.16; stage 1, 7 steps of 2.04 + 0.5 x 2.04^2; stage 2, 3 steps of
    # 8.16 + 0.1 x 8.16^2; decode -10 + 63.19 megapixels of frames.
    assert run_seconds(model, 960, 544, 121) == pytest.approx(136.65232)
    # A short clip decodes in no time, never in less.
    assert run_seconds(model, 256, 256, 9) == pytest.approx(2.7444992)


def test_a_generate_clip_pays_the_fixed_part_once_and_the_scaled_fit():
    estimate = estimate_clip(FLAT, 960, 544, 121)

    assert estimate.basis == "provisional"
    assert (estimate.steps, estimate.width, estimate.height, estimate.reference_count) == (11, 960, 544, 0)
    assert (estimate.setup_seconds, estimate.per_item_seconds, estimate.total_seconds) == (60.0, 30.0, 90.0)
    assert estimate.excludes == ("weight download",)


def test_a_clip_without_the_prompt_pass_saves_its_seconds():
    estimate = estimate_clip(FLAT, 960, 544, 121, enhance=False)

    assert (estimate.setup_seconds, estimate.total_seconds) == (40.0, 70.0)


def test_each_lora_adds_its_seconds_to_the_clip():
    assert estimate_clip(FLAT, 960, 544, 121, loras=2).total_seconds == 110.0


def test_an_audio_track_takes_the_guided_path():
    estimate = estimate_clip(FLAT, 960, 544, 121, audio=True)

    assert estimate.steps == 33
    assert estimate.total_seconds == 180.0


def test_a_reference_takes_the_guided_path_only_where_the_model_says_so():
    guided = estimate_clip(FLAT, 960, 544, 121, references=1)
    distilled = estimate_clip(replace(FLAT, guided_with_references=False), 960, 544, 121, references=1)

    assert (guided.steps, guided.total_seconds, guided.reference_count) == (33, 180.0, 1)
    assert (distilled.steps, distilled.total_seconds) == (11, 90.0)


def test_an_edit_follows_the_edit_fit_times_the_effect_and_never_enhances():
    estimate = estimate_clip(FLAT, 960, 544, 121, audio=True, adapter=EFFECT)
    cheaper = estimate_clip(FLAT, 960, 544, 121, adapter=replace(EFFECT, cost_factor=0.5))

    # 5 + 100 x 8.16 = 821 s. An edit takes no audio path and no prompt pass.
    assert (estimate.steps, estimate.setup_seconds, estimate.total_seconds) == (8, 40.0, 820.0)
    assert cheaper.total_seconds == 410.0


def test_a_short_edit_costs_the_loads_at_least():
    estimate = estimate_clip(FLAT, 256, 256, 9, adapter=EFFECT)

    assert (estimate.setup_seconds, estimate.per_item_seconds, estimate.total_seconds) == (40.0, 0.0, 40.0)


def test_an_effect_that_conditions_stage_2_refines_for_three_more_steps():
    refining = replace(EFFECT, stage_2_conditioning=True)

    assert estimate_clip(FLAT, 960, 544, 121, adapter=refining).steps == 11


def test_a_faster_effect_still_pays_the_loads():
    cheap = replace(EFFECT, cost_factor=0.25)
    small = estimate_clip(FLAT, 256, 256, 9, adapter=cheap)
    large = estimate_clip(FLAT, 960, 544, 121, adapter=cheap)

    # The factor scales the fit, 17.8 s here, and not the 40 s of the loads.
    assert (small.setup_seconds, small.per_item_seconds, small.total_seconds) == (40.0, 0.0, 40.0)
    assert large.total_seconds == 210.0  # 821 x 0.25


def test_fast_mode_is_counted_at_the_default_speed_and_says_so():
    estimate = estimate_clip(FLAT, 960, 544, 121, fast_mode=True)

    assert estimate.total_seconds == 90.0
    assert estimate.excludes == ("weight download", FAST_MODE)


def test_a_model_without_constants_names_no_seconds():
    estimate = estimate_clip(None, 960, 544, 121, references=2, audio=True)

    assert estimate.basis == "unavailable"
    assert (estimate.steps, estimate.reference_count) == (33, 2)
    assert estimate.total_seconds is None and estimate.setup_seconds is None
    assert estimate.excludes == ()
