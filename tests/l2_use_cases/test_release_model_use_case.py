import threading

import pytest

from studio.l1_entities.errors import BackendBusy
from studio.l2_use_cases.release_model_use_case import ReleaseModelUseCase
from tests.support.fakes import FakeModelResidencyGateway


def test_leaving_a_workspace_releases_the_resident_model():
    lock = threading.Lock()
    residency = FakeModelResidencyGateway()
    residency.claim("image-model")

    ReleaseModelUseCase(lock, residency).execute()

    assert residency.current is None
    assert residency.events == ["claim image-model", "release image-model"]


def test_workspace_switch_does_not_release_a_model_under_a_run():
    lock = threading.Lock()
    residency = FakeModelResidencyGateway()
    residency.claim("image-model")
    lock.acquire()

    with pytest.raises(BackendBusy):
        ReleaseModelUseCase(lock, residency).execute()

    assert residency.current == "image-model"
    lock.release()


def test_an_explicit_release_takes_the_unconditional_path():
    lock = threading.Lock()

    class Recording(FakeModelResidencyGateway):
        def release(self):
            self.events.append("release all")

        def release_idle(self):
            self.events.append("release idle")

    residency = Recording()

    ReleaseModelUseCase(lock, residency).execute(explicit=True)

    assert residency.events == ["release all"]
