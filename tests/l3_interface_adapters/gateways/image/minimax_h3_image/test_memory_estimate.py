"""Memory estimation for minimax_h3_image, without an engine."""

import pytest

from studio.l3_interface_adapters.gateways.image.minimax_h3_image import memory_estimate
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png, estimate


@pytest.mark.parametrize(
    ("mode", "options"),
    (
        ("generate", {}),  # the form's own default, 1024 square
        ("generate", {"size": "1024x576"}),
        ("generate", {"size": "2048x2048"}),
        ("generate", {"size": "2560x1440"}),
        ("generate", {"loras": "[]"}),
        ("edit", {"size": "match", "references": [encoded_png(1600, 900)]}),
        ("edit", {"size": "2048x2048", "references": [encoded_png(64, 64)] * 4}),
    ),
)
def test_h3_image_uses_its_measured_peak_inside_what_the_form_offers(mode, options):
    assert estimate("image", "minimax_h3_image", mode, **options) == 22.0


@pytest.mark.parametrize(
    ("mode", "options"),
    (
        ("inpaint", {}),
        ("generate", {"size": "4096x2048"}),  # above the 4 MP the measurement reached
        ("generate", {"size": "not-a-size"}),
        ("generate", {"loras": [{"id": "warm"}]}),
        ("generate", {"mask": True}),
        ("generate", {"each_reference": True}),
        ("edit", {"references": [encoded_png(64, 64)] * 5}),
        ("edit", {"references": [encoded_png(410, 100)]}),  # the gateway refuses past 4:1
        ("edit", {"size": "match", "references": [encoded_png(4096, 4096)]}),
        ("edit", {"size": "match", "references": [encoded_png(31, 32)]}),
        ("edit", {"size": "match", "references": [encoded_png(255, 256)]}),
        ("edit", {"size": "match", "references": [encoded_png(1041, 3989)]}),
        ("edit", {"size": "match"}),
        ("generate", {"reference_sizes": [[512, 512]]}),  # sizes with no references
    ),
)
def test_h3_image_fails_closed_outside_what_was_measured(mode, options):
    assert estimate("image", "minimax_h3_image", mode, **options) is None


@pytest.mark.parametrize("width,height", [(4096, 4096), (31, 32), (1041, 3989)])
def test_match_estimate_checks_the_reference_dimensions(monkeypatch, width, height):
    calls = []
    original = memory_estimate.match_canvas

    def record_canvas(*dimensions):
        calls.append(dimensions)
        return original(*dimensions)

    monkeypatch.setattr(memory_estimate, "match_canvas", record_canvas)
    assert estimate("image", "minimax_h3_image", "edit", size="match", references=[encoded_png(width, height)]) is None
    assert calls == [(width, height)]
