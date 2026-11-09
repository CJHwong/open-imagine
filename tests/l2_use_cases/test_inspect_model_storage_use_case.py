"""A cleanup preview protects shared and explicitly retained assets."""

from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l2_use_cases.inspect_model_storage_use_case import InspectModelStorageUseCase


def storage():
    def asset(id, models, kind="weights", blocked=""):
        return dict(id=id, models=models, kind=kind, blocked=blocked, bytes=4)

    return Mock(
        inventory=Mock(
            return_value=dict(
                revision="v1",
                models=[dict(id="a"), dict(id="b")],
                assets=[
                    asset("a", ["a"]),
                    asset("shared", ["a", "b"]),
                    asset("runtime", ["a"], "runtime"),
                    asset("external", ["a"], blocked="external"),
                    asset("b", ["b"]),
                ],
            )
        )
    )


def test_preview_default_runtime_and_shared_protection():
    port = storage()
    use = InspectModelStorageUseCase(port)
    assert use.execute() == port.inventory()
    plan = use.execute(["a"])
    assert [a["id"] for a in plan["remove"]] == ["a"]
    assert [a["reason"] for a in plan["retain"]] == ["shared", "runtime", "external"]
    assert use.execute(["a", "b"], True)["bytes"] == 16


@pytest.mark.parametrize(
    "models,runtime", [("a", False), ([], False), ([1], False), (["a", "a"], False), (["missing"], False), (["a"], 1)]
)
def test_invalid_selection(models, runtime):
    with pytest.raises(InvalidJob):
        InspectModelStorageUseCase(storage()).execute(models, runtime)
