"""Memory estimation and admission regression coverage, without engines."""

import base64

import pytest

from studio.l1_entities.errors import InvalidJob
from tests.support.memory_estimates import admission_for as admission_for
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib
from tests.support.memory_estimates import json_list_reference as json_list_reference


@pytest.mark.parametrize("reference", (7, {}, {"png_base64": None}))
def test_reference_sizes_reject_invalid_entries(reference):
    assert estimate("image", "qwen21_turbo", "edit", references=[reference]) is None


@pytest.mark.parametrize("encoded", ("%%%", base64.b64encode(b"not a png").decode("ascii")))
def test_reference_sizes_raise_for_unreadable_images(encoded):
    with pytest.raises(InvalidJob, match="not readable"):
        estimate("image", "qwen21_turbo", "edit", references=[{"png_base64": encoded}])


def test_reference_sizes_read_json_and_data_uri_inputs():
    encoded = encoded_png(512, 512)
    assert estimate(
        "image",
        "qwen21_turbo",
        "edit",
        references=json_list_reference(encoded),
        resolution="match",
    ) == pytest.approx(51.51, abs=0.01)
    assert estimate(
        "image",
        "qwen21_turbo",
        "edit",
        references=[{"data": "data:image/png;base64," + encoded}],
        resolution="match",
    ) == pytest.approx(51.51, abs=0.01)


def test_reference_sizes_reject_bad_json_and_non_list_shapes():
    assert estimate("image", "qwen21_turbo", "edit", references="not-json") is None
    assert estimate("image", "qwen21_turbo", "edit", references={"png_base64": encoded_png(512, 512)}) is None


@pytest.mark.parametrize("value", (1, "12"))
def test_positive_integer_accepts_positive_integer_values(value):
    assert estimate("video", "ltx25_mlx", width=value, height=384, num_frames=25) == 25.0


@pytest.mark.parametrize("value", (True, 0, -1, 1.5, "0", "bad"))
def test_positive_integer_rejects_bad_dimensions(value):
    assert estimate("video", "ltx25_mlx", width=value, height=384, num_frames=25) is None


def test_edit_area_needs_a_reference_for_match():
    from studio.l3_interface_adapters.gateways.memory.inputs import _edit_megapixels

    assert _edit_megapixels("match", (), 1344) is None
