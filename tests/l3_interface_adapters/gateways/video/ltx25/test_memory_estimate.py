"""Memory estimation and admission regression coverage, without engines."""

import pytest

from studio.l3_interface_adapters.gateways.video.ltx25 import memory_estimate as ltx_memory
from tests.support.memory_estimates import admission_for as admission_for
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib
from tests.support.memory_estimates import json_list_reference as json_list_reference


@pytest.mark.parametrize(
    "changes",
    (
        {"mode": "edit"},
        {"audio": "reference"},
        {"has_audio": True},
        {"loras": [{"id": "lora"}]},
        {"reference_count": 1},
        {"references": [{}]},
        {"fast_mode": True},
        {"enhance": False},
        {"width": "bad"},
        {"height": 0},
        {"num_frames": 0},
        {"width": 1921},
        {"height": 1921},
        {"width": 1920, "height": 1089},
        {"num_frames": 98},
    ),
)
def test_ltx_fails_closed_for_unmeasured_modes_and_inputs(changes):
    request = {"width": 384, "height": 384, "num_frames": 25, **changes}
    assert estimate("video", "ltx25_mlx", **request) is None


def test_ltx_estimates_its_largest_declared_clip():
    assert estimate("video", "ltx25_mlx", width=1920, height=1088, num_frames=97) == 54.0


def test_ltx_fails_closed_when_token_shape_exceeds_the_measured_limit(monkeypatch):
    monkeypatch.setattr(ltx_memory, "tokens", lambda *args: ltx_memory.LTX_LARGE_TOKENS + 1)

    assert estimate("video", "ltx25_mlx", width=384, height=384, num_frames=25) is None
