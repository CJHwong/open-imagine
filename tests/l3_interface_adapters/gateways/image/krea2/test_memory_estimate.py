"""Memory estimation and admission regression coverage, without engines."""

import pytest

from tests.support.memory_estimates import admission_for as admission_for
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib
from tests.support.memory_estimates import json_list_reference as json_list_reference


@pytest.mark.parametrize(
    ("options", "peak"),
    (
        ({}, 47.0),  # the form's own default, 1024 square
        ({"size": "512x512"}, 34.0),
        ({"size": "768x432"}, 47.0),  # above 512 square, where 768 square already reached 44.8
        ({"size": "1024x1024"}, 47.0),
        ({"size": "1152x864"}, 47.0),
        ({"size": "match", "references": [encoded_png(1600, 900)]}, 47.0),
        ({"size": "512x512", "references": [encoded_png(4032, 3024)]}, 34.0),
        ({"loras": "[]"}, 47.0),
    ),
)
def test_krea2_uses_its_measured_peak_for_text_and_one_reference(options, peak):
    assert estimate("image", "krea2", **options) == peak


@pytest.mark.parametrize(
    ("mode", "options"),
    (
        ("edit", {}),
        ("generate", {"size": "1280x1024"}),  # above the 1 MP the measurement reached
        ("generate", {"size": "not-a-size"}),
        ("generate", {"loras": [{"id": "warm"}]}),
        ("generate", {"mask": True}),
        ("generate", {"each_reference": True}),
        ("generate", {"reference_sizes": [[512, 512], [512, 512]]}),
        ("generate", {"reference_sizes": [[512, 512]]}),  # sizes with no references
    ),
)
def test_krea2_fails_closed_outside_what_was_measured(mode, options):
    assert estimate("image", "krea2", mode, **options) is None
