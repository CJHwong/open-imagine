"""A catalog can admit new estimators without knowing their model or runtime."""

from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import InsufficientMemory
from studio.l3_interface_adapters.api.resource_admission import GIB, ResourceAdmission
from studio.l3_interface_adapters.gateways.in_memory.studio_settings_gateway import InMemoryStudioSettingsGateway
from studio.l3_interface_adapters.gateways.memory.catalog_memory_estimate_gateway import CatalogMemoryEstimateGateway


def test_custom_estimator_is_selected_without_importing_a_model(monkeypatch):
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.memory.catalog_memory_estimate_gateway.sys.platform", "darwin"
    )
    estimator = Mock(return_value=12.0)
    catalog = CatalogMemoryEstimateGateway({("image", "new_model"): estimator})
    request = {"kind": "image", "backend": "new_model", "mode": "edit"}
    ResourceAdmission(lambda: (64 * GIB, 32 * GIB), catalog, InMemoryStudioSettingsGateway(True))(request)
    estimator.assert_called_once_with(request)
    with pytest.raises(InsufficientMemory, match=r"12\.0 GiB"):
        ResourceAdmission(lambda: (64 * GIB, 16 * GIB), catalog, InMemoryStudioSettingsGateway(True))(request)


def test_unmeasured_models_do_not_call_an_unrelated_estimator(monkeypatch):
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.memory.catalog_memory_estimate_gateway.sys.platform", "darwin"
    )
    estimator = Mock(side_effect=AssertionError("wrong estimator"))
    catalog = CatalogMemoryEstimateGateway({("image", "other"): estimator})
    assert catalog.estimate({"kind": "image", "backend": "unmeasured"}, 64) is None
    estimator.assert_not_called()
