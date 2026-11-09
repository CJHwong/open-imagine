"""Remove a reviewed selection under the same lock as generation and model loading."""

from studio.l1_entities.errors import BackendBusy, InvalidJob
from studio.l2_use_cases.inspect_model_storage_use_case import InspectModelStorageUseCase


class RemoveModelAssetsUseCase:
    def __init__(self, storage, engine_lock, residency):
        self._storage = storage
        self._lock = engine_lock
        self._residency = residency

    def execute(self, models, include_runtime, revision):
        if not self._lock.acquire(blocking=False):
            raise BackendBusy("Wait for the current operation to finish before removing model files.")
        try:
            plan = InspectModelStorageUseCase(self._storage).execute(models, include_runtime)
            if not isinstance(revision, str) or revision != plan["revision"]:
                raise InvalidJob("Model files changed. Review the cleanup preview again.")
            if not plan["remove"]:
                raise InvalidJob("No removable files in this selection.")
            self._residency.release()
            return self._storage.remove(tuple(asset["id"] for asset in plan["remove"]), revision)
        finally:
            self._lock.release()
