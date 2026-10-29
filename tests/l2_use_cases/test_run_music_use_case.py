import threading
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import BackendBusy, BackendChanged, Cancelled
from studio.l1_entities.music_job import MusicJob, MusicResult
from studio.l2_use_cases.run_music_use_case import RunMusicUseCase
from studio.l3_interface_adapters.gateways.in_memory_music_backend_catalog_gateway import (
    InMemoryMusicBackendCatalogGateway,
)
from studio.l3_interface_adapters.gateways.in_memory_progress_gateway import InMemoryProgressGateway


def setup(catalog=False):
    backend, residency = Mock(), Mock()
    backend.run.side_effect = lambda job, step, stop: MusicResult(b"wav", 1, 48000, job.seed)
    progress, lock = InMemoryProgressGateway(), threading.Lock()
    models = InMemoryMusicBackendCatalogGateway({"yue2": backend}, "yue2", ("yue2",)) if catalog else None
    return RunMusicUseCase(backend, progress, lock, residency, models), backend, progress, lock, residency


def job(seed=7):
    return MusicJob("pop", "[Verse]\nhello", seed)


@pytest.mark.parametrize("catalog", [False, True])
def test_music_run_shares_model_slot_and_releases_lock(catalog):
    usecase, backend, progress, lock, residency = setup(catalog)
    assert usecase.execute(job()).seed == 7
    residency.activate.assert_called_once_with("yue2")
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
