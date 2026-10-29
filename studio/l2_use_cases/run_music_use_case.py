"""Run music in the studio's shared memory slot."""

import threading

from studio.l1_entities.errors import BackendBusy, BackendChanged, Cancelled
from studio.l1_entities.music_job import MusicJob, MusicResult
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.music_backend_catalog_gateway import MusicBackendCatalogGateway
from studio.l2_use_cases.boundaries.music_backend_gateway import MusicBackendGateway
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway


class RunMusicUseCase:
    def __init__(
        self,
        backend: MusicBackendGateway,
        progress: ProgressGateway,
        engine_lock: threading.Lock,
        residency: ModelResidencyGateway,
        catalog: MusicBackendCatalogGateway | None = None,
    ):
        self._backend = backend
        self._progress = progress
        self._engine_lock = engine_lock
        self._residency = residency
        self._catalog = catalog

    def execute(self, job: MusicJob, backend_id: str = "yue2") -> MusicResult:
        return self.execute_batch([job], lambda index, result: None, lambda index, total: None, backend_id)[0]

    def execute_batch(self, jobs, completed, started, backend_id="yue2"):
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("The model is busy. Wait for it, or cancel the active operation.")
        try:
            if self._catalog is not None and backend_id != self._catalog.active_id():
                raise BackendChanged("The Music model changed in another tab. Reload the page.")
            if self._catalog is not None:
                self._backend = self._catalog.get(backend_id)
            self._progress.clear_cancel()
            self._progress.begin("", kind="music")
            self._residency.activate(backend_id)
            return self._run_loaded(jobs, completed, started)
        finally:
            self._progress.finish()
            self._engine_lock.release()

    def _run_loaded(self, jobs, completed, started):
        finished = threading.Event()
        watcher = threading.Thread(target=self._watch_loading, args=(finished,), daemon=True)
        watcher.start()
        try:
            self._backend.load()
            return self._make_takes(jobs, completed, started)
        except Exception:
            if self._progress.cancel_requested():
                raise Cancelled("Music generation was cancelled.") from None
            raise
        finally:
            finished.set()
            watcher.join()

    def _make_takes(self, jobs, completed, started):
        results = []
        for index, job in enumerate(jobs, start=1):
            if self._progress.cancel_requested():
                raise Cancelled("Music generation was cancelled.")
            self._progress.begin("", kind="music")
            started(index, len(jobs))
            result = self._backend.run(job, self._progress.set_step, self._progress.cancel_requested)
            completed(index, result)
            results.append(result)
        return results

    def _watch_loading(self, finished: threading.Event) -> None:
        while not finished.wait(0.1):
            if self._progress.cancel_requested():
                self._backend.release()
                return
