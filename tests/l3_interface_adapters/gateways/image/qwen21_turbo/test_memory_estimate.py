"""Memory estimation and admission regression coverage, without engines."""

import pytest

from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib


def reference(size=(1024, 1024)):
    return {"png_base64": encoded_png(*size)}


def test_generate_uses_the_measured_small_and_large_steps():
    assert estimate("image", "qwen21_turbo", size="512x512") == 31.0
    assert estimate("image", "qwen21_turbo", size="768x768") == 31.0
    assert estimate("image", "qwen21_turbo", size="1024x1024") == 52.0
    assert estimate("image", "qwen21_turbo", size="1328x1328") == 52.0


def test_generate_uses_the_pixel_area_below_one_megapixel():
    assert estimate("image", "qwen21_turbo", size="1024x576") == 31.0


def test_match_generate_uses_one_megapixel():
    assert estimate("image", "qwen21_turbo", size="match") == 52.0


def test_edit_is_linear_in_output_area_and_reference_count():
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution="1024") == pytest.approx(
        52.02, abs=0.01
    )
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()] * 4, resolution="1024") == pytest.approx(
        57.78, abs=0.01
    )
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()] * 10, resolution="1024") == pytest.approx(
        69.3, abs=0.01
    )


def test_edit_output_size_moves_the_peak():
    small = estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution="512")
    large = estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution="1024")

    assert small == pytest.approx(51.51, abs=0.01)
    assert large > small


def test_an_edit_above_1_2_megapixels_takes_the_56_gib_floor():
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution="1344") == 56.0


def test_a_mask_counts_as_one_more_reference():
    assert estimate(
        "image", "qwen21_turbo", "edit", references=[reference(), reference()], resolution="1024", mask=True
    ) == pytest.approx(53.94, abs=0.01)


def test_each_reference_keeps_one_image_in_memory():
    assert estimate(
        "image", "qwen21_turbo", "edit", references=[reference()] * 4, resolution="1024", each_reference=True
    ) == pytest.approx(52.02, abs=0.01)


def test_match_uses_the_last_reference_and_its_cap():
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution="match") == pytest.approx(
        52.02, abs=0.01
    )
    assert estimate("image", "qwen21_turbo", "edit", references=[reference((4032, 3024))], resolution="match") == 56.0


def test_edit_fails_closed_without_a_reference_or_with_too_many():
    assert estimate("image", "qwen21_turbo", "edit", references=[], resolution="1024") is None
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()] * 11, resolution="1024") is None


def test_a_mask_needs_a_picture_beside_it():
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution="1024", mask=True) is None


def test_edit_accepts_a_numeric_side_and_refuses_an_unknown_one():
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution="768") == pytest.approx(
        51.72, abs=0.01
    )
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution=768) == pytest.approx(
        51.72, abs=0.01
    )
    assert estimate("image", "qwen21_turbo", "edit", references=[reference()], resolution="bad") is None


def test_an_unmeasured_quantization_fails_closed():
    payload = {"kind": "image", "backend": "qwen21_turbo", "size": "1024x1024"}

    assert estimate_peak_gib(payload, 64, qwen_turbo_quantize=8) is None


def test_an_unmeasured_lora_fails_closed():
    assert estimate("image", "qwen21_turbo", size="512x512", loras=[{"id": "extra"}]) is None


@pytest.mark.parametrize("size", (None, 512, "bad-size", "2048x2048"))
def test_generate_fails_closed_for_invalid_or_oversized_shapes(size):
    assert estimate("image", "qwen21_turbo", size=size) is None


def test_generate_fails_closed_when_a_reference_is_present():
    assert estimate("image", "qwen21_turbo", references=[reference()]) is None


@pytest.mark.parametrize("flag", ("mask", "each_reference"))
def test_generate_fails_closed_for_reference_modes(flag):
    assert estimate("image", "qwen21_turbo", size="512x512", **{flag: True}) is None


def test_other_modes_are_unmeasured():
    assert estimate("image", "qwen21_turbo", "plan", size="512x512") is None


@pytest.mark.parametrize("loras", (None, "", "[]", []))
def test_empty_lora_selections_are_not_extra_weights(loras):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=loras) is not None


@pytest.mark.parametrize("loras", ([{"id": "extra"}], "[{}]", "not-json"))
def test_nonempty_or_invalid_loras_are_unmeasured(loras):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=loras) is None


def test_an_edit_that_needs_an_unreadable_reference_is_refused():
    from studio.l1_entities.errors import InvalidJob

    with pytest.raises(InvalidJob, match="not readable"):
        estimate("image", "qwen21_turbo", "edit", references=[{"png_base64": "bad"}], resolution="1024")
