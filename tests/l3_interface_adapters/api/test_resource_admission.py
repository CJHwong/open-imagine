"""Memory estimation and admission regression coverage, without engines."""

import pytest

from studio.l1_entities.errors import InsufficientMemory
from studio.l3_interface_adapters.api.resource_admission import GIB
from tests.support.memory_estimates import admission_for as admission_for
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform
from tests.support.memory_estimates import encoded_png as encoded_png
from tests.support.memory_estimates import estimate as estimate
from tests.support.memory_estimates import estimate_peak_gib as estimate_peak_gib
from tests.support.memory_estimates import json_list_reference as json_list_reference


def test_admission_allows_qwen_when_quantization_is_not_calibrated():
    admission = admission_for(lambda: (64 * GIB, 64 * GIB), qwen_turbo_quantize=8)

    assert admission({"kind": "image", "backend": "qwen21_turbo", "size": "1024x1024"}) is None


def test_qwen_generation_blocks_when_free_memory_cannot_hold_the_peak_and_reserve():
    admission = admission_for(lambda: (64 * GIB, 59 * GIB))

    with pytest.raises(InsufficientMemory):
        admission(
            {
                "kind": "image",
                "backend": "qwen21_turbo",
                "mode": "generate",
                "size": "1024x1024",
            }
        )


def test_memory_rejection_explains_the_shortfall_and_how_to_retry():
    admission = admission_for(lambda: (64 * GIB, 59 * GIB))

    with pytest.raises(InsufficientMemory) as rejected:
        admission({"kind": "image", "backend": "qwen21_turbo", "size": "1024x1024"})

    message = str(rejected.value)
    assert "Not enough memory to start" in message
    assert "53.1 GiB" in message and "8 GiB reserved" in message
    assert "59.0 GiB is available" in message
    assert "Close other memory-heavy apps" in message
    assert "release the loaded model" in message
    assert "smaller output or fewer references" in message


def test_admission_accepts_a_request_that_fits_with_the_reserve():
    admission = admission_for(lambda: (64 * GIB, 50 * GIB))

    assert admission({"kind": "image", "backend": "qwen21_turbo", "size": "512x512"}) is None


def test_admission_allows_a_request_without_a_measured_model_estimate():
    admission = admission_for(lambda: (64 * GIB, 64 * GIB))

    assert admission({"kind": "image", "backend": "optional-model"}) is None


@pytest.mark.parametrize("resolution", ("match", "512", "768"))
@pytest.mark.parametrize("count", (1, 2))
def test_admission_allows_qwen_edits_without_claiming_a_measured_peak(resolution, count):
    payload = {
        "kind": "image",
        "backend": "qwen21_turbo",
        "mode": "edit",
        "resolution": resolution,
        "references": [{"png_base64": encoded_png(512, 512)}] * count,
    }

    assert estimate_peak_gib(payload, 64) is None
    assert admission_for(lambda: (64 * GIB, 50 * GIB))(payload) is None


def test_krea2_needs_its_peak_and_the_reserve_free():
    fits = admission_for(lambda: (64 * GIB, 55 * GIB))
    short = admission_for(lambda: (64 * GIB, 54 * GIB))

    assert fits({"kind": "image", "backend": "krea2", "size": "1024x1024"}) is None
    with pytest.raises(InsufficientMemory, match=r"about 47\.0 GiB"):
        short({"kind": "image", "backend": "krea2", "size": "1024x1024"})


def test_app_policy_blocks_unmeasured_requests_until_disabled():
    from studio.l1_entities.errors import ResourceEstimateUnavailable
    from studio.l3_interface_adapters.api.resource_admission import ResourceAdmission
    from studio.l3_interface_adapters.gateways.in_memory_studio_settings_gateway import InMemoryStudioSettingsGateway
    from studio.l4_frameworks_and_drivers.memory_estimates import build_memory_estimates

    settings = InMemoryStudioSettingsGateway()
    admission = ResourceAdmission(lambda: (64 * GIB, GIB), build_memory_estimates(), settings)
    payload = {"kind": "video", "backend": "ltx25_mlx", "references": ["unmeasured"]}
    with pytest.raises(ResourceEstimateUnavailable, match="Settings > Memory"):
        admission(payload)
    settings.set_require_memory_estimate(False)
    admission(payload)
    with pytest.raises(InsufficientMemory):
        admission({"kind": "image", "backend": "qwen21_turbo", "size": "1024x1024"})


def test_app_policy_requires_every_batch_item_to_be_measured():
    from studio.l1_entities.errors import ResourceEstimateUnavailable
    from studio.l3_interface_adapters.api.resource_admission import ResourceAdmission
    from studio.l3_interface_adapters.gateways.in_memory_studio_settings_gateway import InMemoryStudioSettingsGateway
    from studio.l4_frameworks_and_drivers.memory_estimates import build_memory_estimates

    settings = InMemoryStudioSettingsGateway()
    admission = ResourceAdmission(lambda: (64 * GIB, 64 * GIB), build_memory_estimates(), settings)
    measured = {"mode": "generate", "size": "512x512"}
    unmeasured = {"mode": "edit", "references": [{"png_base64": encoded_png(512, 512)}]}
    batch = {"kind": "image", "backend": "qwen21_turbo", "items": [measured, unmeasured]}
    with pytest.raises(ResourceEstimateUnavailable):
        admission(batch)
    admission({**batch, "items": [measured, measured]})
    settings.set_require_memory_estimate(False)
    admission(batch)
