"""Run one video while sharing the studio's single-model lock."""

import threading
from collections.abc import Callable
from dataclasses import replace

from studio.l1_entities.errors import BackendBusy, BackendChanged, Cancelled
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.progress_gateway import ProgressGateway
from studio.l2_use_cases.boundaries.video_backend_catalog_gateway import VideoBackendCatalogGateway
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway


class RunVideoUseCase:
    def __init__(
        self,
        catalog: VideoBackendCatalogGateway,
        progress: ProgressGateway,
        engine_lock: threading.Lock,
        residency: ModelResidencyGateway,
    ):
        self._catalog = catalog
        self._progress = progress
        self._engine_lock = engine_lock
        self._residency = residency

    def execute(self, job: VideoJob, backend_id: str, request_id: str) -> VideoResult:
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("The model is busy with a run in another tab. Wait for it, or cancel it there.")
        try:
            if backend_id != self._catalog.active_id():
                raise BackendChanged("The video model changed in another tab. Reload the page.")
            backend: VideoBackendGateway = self._catalog.get(backend_id)
            self._progress.clear_cancel()
            self._progress.begin("", kind="video", request_id=request_id)
            try:
                self._residency.activate(backend_id)
                result = backend.run(job, self._progress.set_step, self._progress.cancel_requested)
                return replace(result, loras=job.loras)
            except Cancelled:
                self._progress.clear_cancel()
                raise
            except Exception:
                if self._progress.cancel_requested():
                    self._progress.clear_cancel()
                    raise Cancelled("video generation was cancelled") from None
                raise
            finally:
                self._progress.finish()
        finally:
            self._engine_lock.release()

    def cancel(self, request_id: str) -> bool:
        """Stop one video request only when it still owns shared progress."""
        return self._progress.request_cancel(request_id)

    def execute_batch(
        self,
        jobs: list[VideoJob],
        backend_id: str,
        request_id: str,
        completed: Callable[[int, VideoResult], None],
        started: Callable[[int, int], None],
        cancelled: Callable[[], bool],
    ) -> list[VideoResult]:
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("The model is busy with a run in another tab. Wait for it, or cancel it there.")
        try:
            if backend_id != self._catalog.active_id():
                raise BackendChanged("The video model changed in another tab. Reload the page.")
            self._progress.clear_cancel()
            self._progress.begin("Preparing clips", kind="video", request_id=request_id)
            self._residency.activate(backend_id)

            def begin(index: int, total: int) -> None:
                self._progress.begin(f"{index} of {total}", kind="video", request_id=request_id)
                started(index, total)

            # Each clip carries the LoRAs it ran with. A batch has one set, so the first
            # job's picks are every clip's.
            def done(index: int, result: VideoResult) -> None:
                completed(index, replace(result, loras=jobs[0].loras))

            results = self._catalog.get(backend_id).run_batch(
                jobs,
                done,
                begin,
                self._progress.set_step,
                lambda: cancelled() or self._progress.cancel_requested(),
            )
            return [replace(result, loras=jobs[0].loras) for result in results]
        except Exception:
            if cancelled() or self._progress.cancel_requested():
                self._progress.clear_cancel()
                raise Cancelled("The video batch was cancelled.") from None
            raise
        finally:
            self._progress.finish()
            self._engine_lock.release()
