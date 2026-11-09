"""Memory estimation and admission regression coverage, without engines."""

import pytest

from tests.support.memory_estimates import admission_for as admission_for
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib
from tests.support.memory_estimates import json_list_reference as json_list_reference


def test_yue2_uses_the_engine_default_token_budget_for_each_mode():
    plan = estimate("music", "yue2", mode="plan")
    generate = estimate("music", "yue2", mode="generate")

    assert plan == pytest.approx(10.4096)
    assert generate == pytest.approx(10.9)


def test_yue_transcription_uses_its_fixed_limit():
    assert estimate("music", "yue2", "transcribe") == 16.0


@pytest.mark.parametrize(
    "payload",
    (
        {"mode": "clone"},
        {"lyrics": 7},
        {"style": 7},
        {"abc": 7},
        {"lyrics": "x" * 20_001},
        {"style": "x" * 4_001},
        {"abc": "x" * 100_001},
        {"sampling": "bad"},
        {"sampling": {"max_tokens": True}},
        {"sampling": {"max_tokens": 0}},
        {"sampling": {"max_tokens": 16_001}},
    ),
)
def test_yue_fails_closed_for_unknown_or_oversized_inputs(payload):
    assert estimate("music", "yue2", **payload) is None


def test_yue_counts_text_sampling_instrumental_and_cover_work():
    regular = estimate("music", "yue2", "generate", style="piano", sampling={"max_tokens": 100})
    instrumental = estimate("music", "yue2", "generate", style="piano", instrumental=True, sampling={"max_tokens": 100})
    cover = estimate("music", "yue2", "cover", style="piano", sampling={"max_tokens": 100})
    long_cover = estimate(
        "music", "yue2", "cover", lyrics="x" * 20_000, instrumental=True, sampling={"max_tokens": 16_000}
    )

    assert regular is not None and instrumental == pytest.approx(regular + 2.0)
    assert cover == 16.0
    assert long_cover is not None and long_cover > 16.0
