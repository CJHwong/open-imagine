"""Return model memory when the user leaves its workspace, or when they ask for it.

The page leaves a workspace on every tab switch. Under a boundary policy that leave
keeps the loaded models, because the boundary decides when one goes. An explicit
release still frees every model.
"""

import threading

from studio.l1_entities.errors import BackendBusy
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway


class ReleaseModelUseCase:
    def __init__(self, engine_lock: threading.Lock, residency: ModelResidencyGateway):
        self._engine_lock = engine_lock
        self._residency = residency

    def execute(self, explicit: bool = False) -> None:
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("Wait for the run to end before switching workspaces.")
        try:
            if explicit:
                self._residency.release()
            else:
                self._residency.release_idle()
        finally:
            self._engine_lock.release()
