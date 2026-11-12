import threading
from collections.abc import Mapping

from studio.l1_entities.errors import UnknownBackend
from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway

IMMEDIATE = "immediate"
BOUNDARY = "boundary"


class InMemoryModelResidencyGateway(ModelResidencyGateway):
    """Free the previous owner at once, or keep loaded models under a memory boundary.

    Under `boundary`, a claim frees from the front of the resident list until the new
    model fits, and a model that is already resident keeps its place. A model with no
    measured footprint is never kept, because its cost cannot be counted; claiming one
    frees every resident model first.
    """

    def __init__(
        self,
        backends: Mapping[str, ModelLifecycleGateway],
        *,
        policy: str = IMMEDIATE,
        boundary_gib: float | None = None,
        footprints: Mapping[str, float] | None = None,
    ):
        if policy not in (IMMEDIATE, BOUNDARY):
            raise ValueError(f"unknown memory policy {policy!r}")
        if policy == BOUNDARY and boundary_gib is None:
            raise ValueError("a boundary policy needs a boundary in GiB")
        self._backends = dict(backends)
        self._policy = policy
        self._boundary_gib = boundary_gib
        self._footprints = dict(footprints or {})
        self._resident: list[str] = []
        self._active_id: str | None = None
        self._lock = threading.RLock()

    def select(self, backend_id: str) -> None:
        with self._lock:
            self._check(backend_id)
            if self._policy == IMMEDIATE and backend_id != self._active_id:
                self._release_all()
            self._active_id = backend_id

    def claim(self, backend_id: str) -> tuple[str, ...]:
        with self._lock:
            self._check(backend_id)
            if self._policy == IMMEDIATE:
                freed = self._release_all(except_id=backend_id)
                self._keep(backend_id)
                self._active_id = backend_id
                return tuple(freed)
            if backend_id in self._resident:
                self._active_id = backend_id
                return ()
            footprint = self._footprints.get(backend_id)
            if footprint is None:
                self._active_id = backend_id
                return tuple(self._release_all())
            boundary = self._boundary_gib
            assert boundary is not None  # the constructor refuses a boundary policy without one
            freed = []
            while self._resident and self._used() + footprint > boundary:
                freed.append(self._release_one(self._resident[0]))
            self._keep(backend_id)
            self._active_id = backend_id
            return tuple(freed)

    def release_active(self) -> None:
        with self._lock:
            if self._active_id is not None and self._active_id in self._resident:
                self._release_one(self._active_id)
            self._active_id = None

    def release_idle(self) -> None:
        with self._lock:
            if self._policy == IMMEDIATE:
                self._release_all()
                self._active_id = None

    def release(self) -> None:
        with self._lock:
            self._release_all()
            self._active_id = None

    def active_id(self) -> str | None:
        with self._lock:
            return self._active_id

    def resident_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._resident)

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "policy": self._policy,
                "boundary_gib": self._boundary_gib,
                "resident": list(self._resident),
            }

    def _check(self, backend_id: str) -> None:
        if backend_id not in self._backends:
            raise UnknownBackend(f"no runtime registered as {backend_id}")

    def _keep(self, backend_id: str) -> None:
        if backend_id not in self._resident:
            self._resident.append(backend_id)

    def _used(self) -> float:
        return sum(self._footprints.get(name, 0.0) for name in self._resident)

    def _release_all(self, except_id: str | None = None) -> list[str]:
        freed = []
        for backend_id in list(self._resident):
            if backend_id == except_id:
                continue
            freed.append(self._release_one(backend_id))
        return freed

    def _release_one(self, backend_id: str) -> str:
        self._backends[backend_id].release()
        self._resident.remove(backend_id)
        return backend_id
