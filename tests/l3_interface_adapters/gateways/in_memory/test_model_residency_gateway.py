import pytest

from studio.l1_entities.errors import UnknownBackend
from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway
from studio.l3_interface_adapters.gateways.in_memory.model_residency_gateway import (
    InMemoryModelResidencyGateway,
)


class Runtime(ModelLifecycleGateway):
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def release(self) -> None:
        self.events.append("release " + self.name)


def gateway(events, names, **options):
    return InMemoryModelResidencyGateway({name: Runtime(name, events) for name in names}, **options)


def boundary(events, footprints, boundary_gib=50.0):
    return InMemoryModelResidencyGateway(
        {name: Runtime(name, events) for name in footprints},
        policy="boundary",
        boundary_gib=boundary_gib,
        footprints=footprints,
    )


def test_claiming_a_different_model_releases_the_previous_model_without_loading_the_new_one():
    events = []
    residency = gateway(events, ("image", "video"))

    residency.claim("image")
    freed = residency.claim("video")

    assert events == ["release image"]
    assert freed == ("image",)
    assert residency.active_id() == "video"
    assert residency.resident_ids() == ("video",)


def test_claiming_the_same_model_keeps_it_resident():
    events = []
    residency = gateway(events, ("image",))
    residency.claim("image")

    freed = residency.claim("image")

    assert events == []
    assert freed == ()
    assert residency.resident_ids() == ("image",)


def test_select_frees_the_previous_model_under_an_immediate_policy():
    events = []
    residency = gateway(events, ("image", "video"))
    residency.claim("image")

    residency.select("video")

    assert events == ["release image"]
    assert residency.active_id() == "video"
    assert residency.resident_ids() == ()


def test_releasing_an_idle_model_is_safe():
    events = []
    residency = gateway(events, ("image",))

    residency.release()
    residency.release_active()
    residency.release_idle()
    residency.claim("image")
    residency.release()

    assert events == ["release image"]
    assert residency.active_id() is None


def test_a_model_outside_the_registry_is_refused():
    residency = InMemoryModelResidencyGateway({})

    with pytest.raises(UnknownBackend, match="no runtime registered as missing"):
        residency.select("missing")
    with pytest.raises(UnknownBackend, match="no runtime registered as missing"):
        residency.claim("missing")


def test_a_boundary_policy_keeps_models_that_fit_together():
    events = []
    residency = boundary(events, {"small": 10.0, "other": 20.0})

    residency.claim("small")
    freed = residency.claim("other")

    assert events == []
    assert freed == ()
    assert residency.resident_ids() == ("small", "other")


def test_a_boundary_policy_frees_the_oldest_model_first_until_the_new_one_fits():
    events = []
    residency = boundary(events, {"small": 10.0, "other": 20.0, "large": 45.0})

    residency.claim("small")
    residency.claim("other")
    freed = residency.claim("large")

    assert events == ["release small", "release other"]
    assert freed == ("small", "other")
    assert residency.resident_ids() == ("large",)


def test_a_resident_model_keeps_its_place_in_the_fifo_order():
    events = []
    residency = boundary(events, {"small": 10.0, "other": 20.0, "large": 45.0})

    residency.claim("small")
    residency.claim("other")
    residency.claim("small")
    freed = residency.claim("large")

    assert freed == ("small", "other")
    assert events == ["release small", "release other"]


def test_a_model_with_no_footprint_frees_every_resident_model_and_is_not_kept():
    events = []
    residency = InMemoryModelResidencyGateway(
        {name: Runtime(name, events) for name in ("small", "unknown")},
        policy="boundary",
        boundary_gib=50.0,
        footprints={"small": 10.0},
    )

    residency.claim("small")
    freed = residency.claim("unknown")

    assert freed == ("small",)
    assert events == ["release small"]
    assert residency.resident_ids() == ()


def test_a_model_larger_than_the_boundary_evicts_the_others_and_still_runs():
    events = []
    residency = boundary(events, {"small": 10.0, "huge": 80.0})

    residency.claim("small")
    freed = residency.claim("huge")

    assert freed == ("small",)
    assert residency.resident_ids() == ("huge",)


def test_select_keeps_every_model_under_a_boundary_policy():
    events = []
    residency = boundary(events, {"small": 10.0, "other": 20.0})

    residency.claim("small")
    residency.select("other")

    assert events == []
    assert residency.resident_ids() == ("small",)
    assert residency.active_id() == "other"


def test_leaving_a_workspace_keeps_the_models_under_a_boundary_policy():
    events = []
    residency = boundary(events, {"small": 10.0})
    residency.claim("small")

    residency.release_idle()

    assert events == []
    assert residency.resident_ids() == ("small",)


def test_an_explicit_release_frees_every_model_under_a_boundary_policy():
    events = []
    residency = boundary(events, {"small": 10.0, "other": 20.0})
    residency.claim("small")
    residency.claim("other")

    residency.release()

    assert events == ["release small", "release other"]
    assert residency.resident_ids() == ()
    assert residency.active_id() is None


def test_releasing_the_active_model_keeps_the_other_residents():
    events = []
    residency = boundary(events, {"small": 10.0, "other": 20.0})
    residency.claim("small")
    residency.claim("other")

    residency.release_active()

    assert events == ["release other"]
    assert residency.resident_ids() == ("small",)


def test_a_boundary_policy_needs_a_boundary_value():
    with pytest.raises(ValueError, match="needs a boundary in GiB"):
        InMemoryModelResidencyGateway({"image": Runtime("image", [])}, policy="boundary")


def test_an_unknown_policy_is_refused():
    with pytest.raises(ValueError, match="unknown memory policy"):
        InMemoryModelResidencyGateway({"image": Runtime("image", [])}, policy="lazy")


def test_status_reports_the_policy_boundary_and_resident_models():
    residency = boundary([], {"small": 10.0})
    residency.claim("small")

    assert residency.status() == {"policy": "boundary", "boundary_gib": 50.0, "resident": ["small"]}
