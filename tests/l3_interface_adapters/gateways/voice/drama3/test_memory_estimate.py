"""Memory estimation and admission regression coverage, without engines."""

import pytest

from studio.l3_interface_adapters.gateways.memory import catalog_memory_estimate_gateway as memory_catalog
from tests.support.memory_estimates import admission_for as admission_for
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib
from tests.support.memory_estimates import json_list_reference as json_list_reference


def test_drama_uses_the_measured_mac_peak_and_prompt_length(monkeypatch):
    monkeypatch.setattr(memory_catalog.sys, "platform", "darwin")

    assert estimate("voice", "drama3", text="") == pytest.approx(47.0)
    assert estimate("voice", "drama3", prompt="word") > estimate("voice", "drama3", text="")


@pytest.mark.parametrize("payload", ({"mode": "clone"}, {"reference": {"wav_base64": "audio"}}, {"text": 7}))
def test_drama_fails_closed_for_references_modes_or_bad_text(payload):
    assert estimate("voice", "drama3", **payload) is None
