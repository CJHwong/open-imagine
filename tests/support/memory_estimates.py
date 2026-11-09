"""Calibrated estimator fixtures and composition helpers; no model runs."""

import base64
import io
import json

import pytest
from PIL import Image

from studio.l3_interface_adapters.api.resource_admission import ResourceAdmission
from studio.l3_interface_adapters.gateways.in_memory.studio_settings_gateway import InMemoryStudioSettingsGateway
from studio.l3_interface_adapters.gateways.memory import catalog_memory_estimate_gateway as memory_catalog
from studio.l3_interface_adapters.gateways.model_catalog.registry import build_memory_estimates
from studio.l4_frameworks_and_drivers.config import Config


def estimate_peak_gib(payload, total_memory_gib, *, qwen_turbo_quantize=None):
    return build_memory_estimates(Config("", (), "", (), {"qwen21_turbo": {"quantize": qwen_turbo_quantize}})).estimate(
        payload, total_memory_gib
    )


def admission_for(headroom, qwen_turbo_quantize=None):
    return ResourceAdmission(
        headroom,
        build_memory_estimates(Config("", (), "", (), {"qwen21_turbo": {"quantize": qwen_turbo_quantize}})),
        InMemoryStudioSettingsGateway(False),
    )


@pytest.fixture(autouse=True)
def calibrated_mac_estimate_platform(monkeypatch):
    monkeypatch.setattr(memory_catalog.sys, "platform", "darwin")


def encoded_png(width, height):
    image = Image.new("RGB", (width, height), (90, 120, 150))
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    return base64.b64encode(encoded.getvalue()).decode("ascii")


def estimate(kind, backend, mode="generate", **options):
    return estimate_peak_gib({"kind": kind, "backend": backend, "mode": mode, **options}, 64)


def json_list_reference(encoded):
    return json.dumps([{"png_base64": encoded}])
