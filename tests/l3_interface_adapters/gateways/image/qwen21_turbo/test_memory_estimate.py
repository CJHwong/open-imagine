"""Memory estimation and admission regression coverage, without engines."""

import base64
import io

import pytest
from PIL import Image

from tests.support.memory_estimates import admission_for as admission_for
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib
from tests.support.memory_estimates import json_list_reference as json_list_reference


def test_qwen_generation_uses_the_measured_high_resolution_peak_from_one_megapixel():
    estimate = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "generate",
            "size": "1024x1024",
        },
        64,
    )

    assert estimate == 53.1


def test_qwen_estimate_fails_closed_for_an_unmeasured_quantization():
    payload = {"kind": "image", "backend": "qwen21_turbo", "size": "1024x1024"}

    assert estimate_peak_gib(payload, 64, qwen_turbo_quantize=8) is None


def test_qwen_generation_fails_closed_for_an_unmeasured_lora():
    estimate = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "generate",
            "size": "512x512",
            "loras": [{"id": "extra-weights"}],
        },
        64,
    )

    assert estimate is None


def test_qwen_edit_uses_the_image_size_instead_of_a_client_size_hint():
    image = Image.new("RGB", (1024, 1024), (90, 120, 150))
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    reference = base64.b64encode(encoded.getvalue()).decode("ascii")

    estimate = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "edit",
            "resolution": "match",
            "references": [{"png_base64": reference}],
            "reference_sizes": [[512, 512]],
        },
        64,
    )

    assert estimate is None


def test_qwen_edit_does_not_estimate_from_sizes_without_reference_images():
    estimate = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "edit",
            "resolution": "match",
            "reference_sizes": [[512, 512]],
        },
        64,
    )

    assert estimate is None


@pytest.mark.parametrize("loras", (None, "", "[]", []))
def test_qwen_generation_accepts_empty_lora_selections(loras):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=loras) is not None


@pytest.mark.parametrize("loras", ([{"id": "extra"}], "[{}]", "not-json"))
def test_qwen_generation_fails_closed_for_nonempty_or_invalid_loras(loras):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=loras) is None


@pytest.mark.parametrize("flag", ("mask", "each_reference"))
def test_qwen_generation_fails_closed_for_reference_modes(flag):
    assert estimate("image", "qwen21_turbo", size="512x512", **{flag: True}) is None


@pytest.mark.parametrize("size", (None, 512, "bad-size", "2048x2048"))
def test_qwen_generation_fails_closed_for_invalid_or_oversized_shapes(size):
    assert estimate("image", "qwen21_turbo", size=size) is None


def test_qwen_generation_uses_the_pixel_area_below_one_megapixel():
    assert estimate("image", "qwen21_turbo", size="1024x576") == pytest.approx(36.4, abs=0.1)


def test_qwen_does_not_estimate_unsupported_modes():
    assert estimate("image", "qwen21_turbo", "plan", size="512x512") is None


def test_qwen_generate_fails_closed_when_a_reference_is_present():
    reference = {"png_base64": encoded_png(1, 1)}
    assert estimate("image", "qwen21_turbo", references=[reference]) is None


def test_qwen_edit_requires_one_or_two_readable_references():
    assert estimate("image", "qwen21_turbo", "edit", references=[]) is None
    reference = encoded_png(512, 512)
    assert estimate("image", "qwen21_turbo", "edit", references=[reference] * 3) is None


@pytest.mark.parametrize("flag", ("mask", "each_reference"))
def test_qwen_edit_fails_closed_for_mask_or_each_reference(flag):
    reference = {"png_base64": encoded_png(512, 512)}
    assert estimate("image", "qwen21_turbo", "edit", references=[reference], **{flag: True}) is None


@pytest.mark.parametrize("resolution", ("768", 768, "bad"))
def test_qwen_edit_fails_closed_for_unmeasured_resolutions(resolution):
    reference = {"png_base64": encoded_png(512, 512)}
    assert estimate("image", "qwen21_turbo", "edit", references=[reference], resolution=resolution) is None


@pytest.mark.parametrize("value", (None, 7, "bad", "12x", "x12"))
def test_bad_image_sizes_fail_closed(value):
    assert estimate("image", "qwen21_turbo", size=value) is None


def test_match_image_size_uses_one_megapixel():
    assert estimate("image", "qwen21_turbo", size="match") == pytest.approx(53.1)


@pytest.mark.parametrize("raw", (None, "", [], (), "[]"))
def test_empty_lora_values_are_not_extra_weights(raw):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=raw) is not None


@pytest.mark.parametrize("raw", ("not-json", "[{}]", [{"id": "extra"}]))
def test_nonempty_lora_values_are_unmeasured(raw):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=raw) is None
