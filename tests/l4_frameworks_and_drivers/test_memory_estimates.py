"""Memory estimation and admission regression coverage, without engines."""

import pytest

from studio.l1_entities.errors import InsufficientMemory
from studio.l3_interface_adapters.api.resource_admission import GIB
from studio.l3_interface_adapters.gateways.memory import catalog_memory_estimate_gateway as memory_catalog
from tests.support.memory_estimates import admission_for as admission_for
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib
from tests.support.memory_estimates import json_list_reference as json_list_reference


def test_supported_default_workflows_keep_their_declared_bounds():
    image = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "generate",
            "size": "512x512",
        },
        64,
    )
    video = estimate_peak_gib(
        {
            "kind": "video",
            "backend": "ltx25_mlx",
            "mode": "generate",
            "width": 384,
            "height": 384,
            "num_frames": 25,
        },
        64,
    )

    assert image == pytest.approx(31.7, abs=0.1)
    assert video == 25.0


def test_batch_estimate_uses_the_largest_item_and_output_reserve():
    result = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "items": [{"size": "512x512"}, {"size": "768x768"}],
        },
        64,
    )

    assert result == pytest.approx(36.48, abs=0.01)


def test_unmeasured_batch_items_do_not_bypass_known_memory_limits():
    payload = {
        "kind": "image",
        "backend": "qwen21_turbo",
        "items": [
            {"mode": "edit", "resolution": "512", "references": [encoded_png(512, 512)]},
            {"mode": "generate", "size": "1024x1024"},
        ],
    }

    assert estimate_peak_gib(payload, 64) == pytest.approx(53.225)
    with pytest.raises(InsufficientMemory):
        admission_for(lambda: (64 * GIB, 59 * GIB))(payload)
    assert admission_for(lambda: (64 * GIB, 64 * GIB))(payload) is None


@pytest.mark.parametrize("items", ([], ["bad"], [{"size": "not-a-size"}]))
def test_batch_estimate_fails_closed_for_empty_or_unmeasured_items(items):
    assert estimate_peak_gib({"kind": "image", "backend": "qwen21_turbo", "items": items}, 64) is None


@pytest.mark.parametrize(
    ("kind", "backend"),
    (
        ("image", "other-image"),
        ("video", "other-video"),
        ("voice", "other-voice"),
        ("music", "other-music"),
        ("other", "qwen21_turbo"),
    ),
)
def test_unmeasured_backends_and_kinds_fail_closed(kind, backend):
    assert estimate(kind, backend) is None


@pytest.mark.parametrize(
    "payload",
    (
        {"kind": "image", "backend": "qwen21_turbo", "size": "512x512"},
        {"kind": "video", "backend": "ltx25_mlx", "width": 384, "height": 384, "num_frames": 25},
        {"kind": "video", "backend": "minimax_h3", "width": 512, "height": 288, "num_frames": 73},
        {"kind": "voice", "backend": "drama3", "text": "hello"},
        {"kind": "music", "backend": "yue2", "style": "piano"},
    ),
)
@pytest.mark.parametrize(
    ("platform", "total_memory_gib"),
    (("linux", 64), ("darwin", 128), ("darwin", 32)),
)
def test_all_mode_estimates_fail_closed_outside_the_calibrated_mac_setup(
    monkeypatch, payload, platform, total_memory_gib
):
    monkeypatch.setattr(memory_catalog.sys, "platform", platform)

    result = estimate_peak_gib(payload, total_memory_gib)

    assert result is None
