"""Deletion requires a fresh preview and exclusive ownership of model residency."""

import threading
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import BackendBusy, InvalidJob
from studio.l2_use_cases.remove_model_assets_use_case import RemoveModelAssetsUseCase
from tests.l2_use_cases.test_inspect_model_storage_use_case import storage


def test_remove_and_release_lock_even_on_failure():
    port = storage()
    lock = threading.Lock()
    resident = Mock()
    use = RemoveModelAssetsUseCase(port, lock, resident)
    assert use.execute(["a"], False, "v1") == port.remove.return_value
    port.remove.assert_called_once_with(("a",), "v1")
    resident.release.assert_called_once()
    port.remove.side_effect = OSError("failure")
    with pytest.raises(OSError):
        use.execute(["a"], False, "v1")
    assert not lock.locked()


def test_busy_stale_invalid_and_empty():
    port = storage()
    lock = threading.Lock()
    resident = Mock()
    use = RemoveModelAssetsUseCase(port, lock, resident)
    lock.acquire()
    with pytest.raises(BackendBusy):
        use.execute(["a"], False, "v1")
    lock.release()
    for revision in (None, "stale"):
        with pytest.raises(InvalidJob, match="changed"):
            use.execute(["a"], False, revision)
    port.inventory.return_value["assets"] = []
    with pytest.raises(InvalidJob, match="No removable"):
        use.execute(["a"], False, "v1")
    resident.release.assert_not_called()
    assert not lock.locked()
