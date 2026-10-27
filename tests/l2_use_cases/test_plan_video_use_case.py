"""A video plan: the clip's settings and time, read from the model's capabilities alone."""

from dataclasses import replace

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.lora import Lora, LoraUse
from studio.l1_entities.video_capabilities import VideoAdapter, VideoEstimate, VideoMode
from studio.l2_use_cases.plan_video_use_case import PlanVideoRequest, PlanVideoUseCase
from studio.l3_interface_adapters.gateways.in_memory_video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from tests.support.fakes import FakeVideoBackendGateway, fake_video_capabilities

MODEL = VideoEstimate(load=(10.0, 0.0), stage_1=(0.0, 0.0), stage_2=(0.0, 0.0), decode=(0.0, 0.0), fixed_seconds=50)
EFFECT = VideoAdapter(id="deblur", label="Deblur", hint="", mode="edit", file="deblur.safetensors")


def catalog_with(active="video-fake"):
    capabilities = replace(
        fake_video_capabilities(),
        modes=(VideoMode("generate", "Generate"), VideoMode("edit", "Edit", needs_clip=True)),
        adapters=(EFFECT,),
        loras=(Lora(id="motion", label="Motion"),),
        max_loras=1,
        estimate=MODEL,
    )
    backends = {
        "video-fake": FakeVideoBackendGateway(capabilities=capabilities),
        "video-other": FakeVideoBackendGateway("video-other", "Other video"),
        "video-hidden": FakeVideoBackendGateway("video-hidden"),
    }
    return InMemoryVideoBackendCatalogGateway(backends, active, ("video-fake", "video-other"))


def request(**fields):
    clip = PlanVideoRequest(backend="", mode="generate", width=960, height=544, num_frames=121, frame_rate=24)
    return replace(clip, **fields)


def test_a_generate_plan_holds_the_settings_the_loras_and_the_time():
    response = PlanVideoUseCase(catalog_with()).execute(
        request(enhance=False, fast_mode=True, loras=(LoraUse("motion", 1.0),))
    )

    assert response.backend == "video-fake"
    assert (response.mode, response.count) == ("generate", 1)
    assert response.effective_options == {
        "width": 960,
        "height": 544,
        "num_frames": 121,
        "frame_rate": 24,
        "enhance": False,
        "fast_mode": True,
    }
    assert response.loras == (LoraUse("motion", 1.0),)
    assert response.offers_loras is True
    assert response.estimate.basis == "provisional"
    assert response.estimate.total_seconds == 60.0


def test_an_edit_plan_names_its_effect_and_takes_the_effect_into_the_time():
    response = PlanVideoUseCase(catalog_with()).execute(request(mode="edit", adapter="deblur", adapter_strength=0.7))

    assert response.effective_options["adapter"] == "deblur"
    assert response.effective_options["adapter_strength"] == 0.7
    assert response.estimate.steps == 8


def test_a_model_without_constants_or_loras_says_so():
    response = PlanVideoUseCase(catalog_with()).execute(request(backend="video-other"))

    assert response.offers_loras is False
    assert response.estimate.basis == "unavailable"


def test_a_blank_backend_reads_the_active_model_and_leaves_it_active():
    catalog = catalog_with(active="video-other")

    backend_id, capabilities = PlanVideoUseCase(catalog).capabilities("")

    assert backend_id == "video-other"
    assert capabilities.backend_id == "video-other"
    assert catalog.active_id() == "video-other"


@pytest.mark.parametrize("backend_id", ["video-hidden", "video-missing"])
def test_a_model_that_is_not_offered_gets_no_plan(backend_id):
    with pytest.raises(InvalidJob, match=f"No video model is offered as {backend_id}"):
        PlanVideoUseCase(catalog_with()).capabilities(backend_id)
