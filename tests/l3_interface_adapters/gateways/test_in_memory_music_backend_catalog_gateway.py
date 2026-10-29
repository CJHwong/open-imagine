import threading
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import BackendBusy, UnknownBackend
from studio.l2_use_cases.switch_music_backend_use_case import SwitchMusicBackendUseCase
from studio.l3_interface_adapters.gateways.in_memory_music_backend_catalog_gateway import (
    InMemoryMusicBackendCatalogGateway,
)


def test_catalog_and_switch_share_the_model_residency():
    one, two, residency = Mock(), Mock(), Mock()
    with pytest.raises(UnknownBackend):
        InMemoryMusicBackendCatalogGateway({}, "missing", ())
    catalog = InMemoryMusicBackendCatalogGateway({"one": one, "two": two}, "one", ("one", "two"))
    assert catalog.get("one") is one and catalog.visible_ids() == ("one", "two")
    lock = threading.Lock()
    switch = SwitchMusicBackendUseCase(catalog, lock, residency)
    with pytest.raises(UnknownBackend):
        catalog.get("missing")
    with pytest.raises(UnknownBackend):
        switch.execute("missing")
    switch.execute("one")
    residency.activate.assert_not_called()
    lock.acquire()
    with pytest.raises(BackendBusy):
        switch.execute("two")
    lock.release()
    switch.execute("two")
    assert catalog.active_id() == "two" and not lock.locked()
    residency.activate.assert_called_once_with("two")
