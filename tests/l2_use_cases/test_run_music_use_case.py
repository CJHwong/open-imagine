import threading
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import BackendBusy, BackendChanged, Cancelled, InsufficientMemory
from studio.l1_entities.music_job import MusicJob, MusicResult
from studio.l2_use_cases.run_music_use_case import RunMusicUseCase
from studio.l3_interface_adapters.api.resource_admission import GIB, ResourceAdmission
from studio.l3_interface_adapters.gateways.in_memory.model_residency_gateway import InMemoryModelResidencyGateway
from studio.l3_interface_adapters.gateways.in_memory.music_backend_catalog_gateway import (
    InMemoryMusicBackendCatalogGateway,
)
from studio.l3_interface_adapters.gateways.in_memory.progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory.studio_settings_gateway import InMemoryStudioSettingsGateway


def setup(catalog=False):
    backend, residency = Mock(), Mock()
    backend.run.side_effect = lambda job, step, stop: MusicResult(b"wav", 1, 48000, job.seed)
    progress, lock = InMemoryProgressGateway(), threading.Lock()
    models = InMemoryMusicBackendCatalogGateway({"yue2": backend}, "yue2", ("yue2",)) if catalog else None
    return RunMusicUseCase(backend, progress, lock, residency, models), backend, progress, lock, residency


def job(seed=7):
    return MusicJob("pop", "[Verse]\nhello", seed)


@pytest.mark.parametrize("stage", ["load", "run"])
def test_failed_music_runtime_loses_only_its_own_residency(stage):
    usecase, backend, _, _, _ = setup()
    retained = Mock()
    residency = InMemoryModelResidencyGateway(
        {"yue2": backend, "retained": retained},
        policy="boundary",
        boundary_gib=50,
        footprints={"yue2": 10, "retained": 10},
    )
    residency.claim("retained")
    usecase._residency = residency
    getattr(backend, stage).side_effect = RuntimeError("engine failed")

    with pytest.raises(RuntimeError, match="engine failed"):
        usecase.execute(job())

    assert residency.resident_ids() == ("retained",)
    assert residency.resident_gib("yue2") == 0
    retained.release.assert_not_called()
    backend.release.assert_called_once()
    backend.load.side_effect = None
    backend.run.side_effect = lambda job, step, stop: MusicResult(b"wav", 1, 48000, job.seed)
    assert usecase.execute(job()).seed == 7
    assert residency.resident_ids() == ("retained", "yue2")


def test_failed_cleanup_removes_phantom_memory_and_keeps_its_runtime_for_retry():
    usecase, backend, _, _, _ = setup()
    residency = InMemoryModelResidencyGateway({"yue2": backend}, footprints={"yue2": 10})
    usecase._residency = residency
    backend.load.side_effect = RuntimeError("load failed")
    backend.release.side_effect = [RuntimeError("cleanup failed"), None]

    with pytest.raises(RuntimeError, match="cleanup failed") as failed:
        usecase.execute(job())

    assert str(failed.value.__context__) == "load failed"
    assert residency.resident_ids() == ()
    assert residency.resident_gib("yue2") == 0
    estimates = Mock()
    estimates.estimate.return_value = 10
    admission = ResourceAdmission(
        lambda: (64 * GIB, 15 * GIB), estimates, InMemoryStudioSettingsGateway(True), residency.resident_gib
    )
    with pytest.raises(InsufficientMemory):
        admission({"kind": "music", "backend": "yue2"})
    residency.release_active()
    assert backend.release.call_count == 2
    assert residency.active_id() is None


@pytest.mark.parametrize("catalog", [False, True])
def test_music_run_shares_model_slot_and_releases_lock(catalog):
    usecase, backend, progress, lock, residency = setup(catalog)
    assert usecase.execute(job()).seed == 7
    residency.claim.assert_called_once_with("yue2")
    backend.load.assert_called_once()
    assert not progress.snapshot().running and not lock.locked()


def test_batch_callbacks_run_in_order_under_one_lock():
    usecase, backend, _, lock, _ = setup()
    events = []

    def complete(index, result):
        events.append((index, result.seed))
        assert lock.locked()

    results = usecase.execute_batch([job(), job(8)], complete, lambda *args: None)
    assert [r.seed for r in results] == [7, 8] and events == [(1, 7), (2, 8)]
    backend.load.assert_called_once()


def test_busy_or_changed_model_never_loads():
    usecase, backend, _, lock, _ = setup(True)
    lock.acquire()
    with pytest.raises(BackendBusy):
        usecase.execute(job())
    lock.release()
    with pytest.raises(BackendChanged):
        usecase.execute(job(), "other")
    backend.load.assert_not_called()
    assert not lock.locked()


@pytest.mark.parametrize("cancel", [False, True])
def test_load_failure_releases_slot(cancel):
    usecase, backend, progress, lock, _ = setup()

    def fail():
        if cancel:
            progress.request_cancel()
        raise RuntimeError("load failed")

    backend.load.side_effect = fail
    with pytest.raises(Cancelled if cancel else RuntimeError):
        usecase.execute(job())
    assert not lock.locked() and not progress.snapshot().running


def test_cancel_between_items_keeps_completed_song():
    usecase, _, progress, _, _ = setup()
    completed = []

    def complete(index, result):
        completed.append(result)
        progress.request_cancel()

    with pytest.raises(Cancelled):
        usecase.execute_batch([job(), job(8)], complete, lambda *args: None)
    assert len(completed) == 1


def test_loading_watcher_terminates_its_engine():
    usecase, backend, progress, _, _ = setup()
    finished = Mock()
    finished.wait.side_effect = [False, False]
    progress.cancel_requested = Mock(side_effect=[False, True])
    usecase._watch_loading(finished)
    backend.release.assert_called_once()
