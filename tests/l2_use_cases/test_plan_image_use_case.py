"""An image plan: the run's own checks and settings, with no run."""

from dataclasses import replace

import pytest

from studio.l1_entities.capabilities import Estimate
from studio.l1_entities.errors import InvalidJob, UnsupportedMode
from studio.l1_entities.lora import Lora, LoraUse
from studio.l2_use_cases.plan_image_use_case import PlanImageRequest, PlanImageUseCase
from studio.l3_interface_adapters.gateways.in_memory_backend_catalog_gateway import InMemoryBackendCatalogGateway
from tests.support.fakes import FakeBackendGateway

STYLE = Lora(id="style", label="Style", strength=0.8)


def catalog_with(active="fake"):
    """Two offered backends and one that is registered but hidden. The edit mode of `fake`
    carries constants and a LoRA, so a plan has a figure and a pick to report."""
    fake = FakeBackendGateway()
    edit = replace(
        fake.caps.mode("edit"), estimate=Estimate(1.0, 0.0, 2, True), loras=(STYLE,), max_loras=1, region_marking=True
    )
    fake.caps = replace(fake.caps, modes=(fake.caps.mode("generate"), edit))
    backends = {"fake": fake, "other": FakeBackendGateway("other", "Other"), "hidden": FakeBackendGateway("hidden")}
    return InMemoryBackendCatalogGateway(backends, default_id=active, visible_ids=("fake", "other"))


def plan(**fields):
    return PlanImageUseCase(catalog_with()).execute(replace(PlanImageRequest(mode="edit", options={}), **fields))


def test_a_plan_fills_every_default_and_counts_the_images():
    response = plan(options={"steps": "4"}, reference_sizes=((512, 512), (512, 512)), total=2)

    assert response.backend == "fake"
    assert response.mode == "edit"
    assert response.count == 2
    assert response.effective_options == {"steps": 4}
    assert response.loras == ()
    assert response.offers_loras is True
    assert (response.estimate.per_item_seconds, response.estimate.total_seconds) == (6.0, 12.0)


def test_a_whole_seed_or_a_blank_one_passes():
    assert plan(reference_sizes=((8, 8),), seed=" 7 ").count == 1
    assert plan(reference_sizes=((8, 8),), seed="").count == 1


def test_one_result_per_reference_multiplies_the_count():
    response = plan(reference_sizes=((512, 512),) * 3, total=2, each_reference=True)

    assert response.count == 6
    assert response.estimate.reference_count == 1


def test_a_region_mask_turns_one_result_per_reference_off():
    response = plan(reference_sizes=((512, 512),) * 3, total=1, each_reference=True, mask=True)

    assert response.count == 1
    assert response.estimate.reference_count == 3


def test_the_picked_loras_come_back_at_their_strength():
    response = plan(reference_sizes=((512, 512),), options={"loras": '[{"id": "style"}]'})

    assert response.loras == (LoraUse("style", 0.8),)


def test_a_blank_backend_plans_on_the_active_one_and_a_named_one_leaves_it_active():
    catalog = catalog_with(active="other")
    use_case = PlanImageUseCase(catalog)

    assert use_case.execute(PlanImageRequest(mode="generate", options={})).backend == "other"
    assert use_case.execute(PlanImageRequest(mode="generate", options={}, backend="fake")).backend == "fake"
    assert catalog.active_id() == "other"


@pytest.mark.parametrize(
    ("fields", "error", "message"),
    [
        ({"backend": "hidden"}, InvalidJob, "No image model is offered as hidden"),
        ({"backend": "missing"}, InvalidJob, "No image model is offered as missing"),
        ({"mode": "inpaint"}, UnsupportedMode, "inpaint"),
        ({"reference_sizes": ()}, InvalidJob, "reference"),
        ({"reference_sizes": ((8, 8),), "total": 5}, InvalidJob, "count must be between 1 and 4"),
        ({"reference_sizes": ((8, 8),), "total": 0}, InvalidJob, "count must be between 1 and 4"),
        ({"reference_sizes": ((8, 8),) * 2, "total": 9, "each_reference": True}, InvalidJob, "between 1 and 8"),
        ({"reference_sizes": ((8, 8),), "options": {"steps": "500"}}, InvalidJob, "steps"),
        ({"reference_sizes": ((8, 8),), "seed": "abc"}, InvalidJob, "seed must be a whole number"),
        (
            {"reference_sizes": ((8, 8),), "options": {"loras": '[{"id": "other"}]'}},
            InvalidJob,
            "LoRA must be one of style",
        ),
    ],
)
def test_a_plan_refuses_what_a_run_refuses(fields, error, message):
    with pytest.raises(error, match=message):
        plan(**fields)
