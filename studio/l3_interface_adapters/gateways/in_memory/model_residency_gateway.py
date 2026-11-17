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
        self._owned_id: str | None = None
        self._lock = threading.RLock()

    def resident_gib(self, backend_id: str) -> float:
        with self._lock:
            if backend_id not in self._resident:
                return 0.0
            return self._footprints.get(backend_id, 0.0)

    def select(self, backend_id: str) -> None:
        with self._lock:
            self._check(backend_id)
            freed = self._detach_all() if self._policy == IMMEDIATE and backend_id != self._active_id else []
            self._active_id = backend_id
        self._free(freed)

    def claim(self, backend_id: str) -> tuple[str, ...]:
        with self._lock:
            self._check(backend_id)
            freed, keep = self._plan_claim(backend_id)
        # The engines are freed outside the lock: `status()` and the state poll read this
        # gateway, and a model that takes seconds to free must not hold them. The caller
        # holds the engine lock, so no other claim or free runs beside this one.
        self._free(freed)
        with self._lock:
            if keep:
                self._keep(backend_id)
            self._active_id = backend_id
            self._owned_id = backend_id
        return tuple(freed)

    def _plan_claim(self, backend_id: str) -> tuple[list[str], bool]:
        """Which models this claim frees, and whether the claimed one stays resident.

        A model with no measured footprint is never kept: its cost cannot be counted, so
        it is claimed and freed before the next one arrives.
        """
        if self._policy == IMMEDIATE:
            return self._detach_all(except_id=backend_id), True
        freed = self._detach_unretained(except_id=backend_id)
        if backend_id in self._resident:
            return freed, True
        footprint = self._footprints.get(backend_id)
        if footprint is None:
            return freed + self._detach_all(except_id=backend_id), False
        boundary = self._boundary_gib
        assert boundary is not None  # the constructor refuses a boundary policy without one
        while self._resident and self._used() + footprint > boundary:
            freed.append(self._detach(self._resident[0]))
        return freed, True

    def release_active(self) -> None:
        with self._lock:
            # A failed load cannot supply the resident credit, even if cleanup also fails.
            freed = [self._detach(self._owned_id)] if self._owned_id is not None else []
            self._active_id = None
        self._free(freed, resident_credit=False)

    def release_idle(self) -> None:
        with self._lock:
            if self._policy == IMMEDIATE:
                freed = self._detach_all()
                self._active_id = None
            elif self._owned_id is not None and self._owned_id not in self._resident:
                freed = [self._detach(self._owned_id)]
                self._active_id = None
            else:
                freed = []
        self._free(freed)

    def release(self) -> None:
        with self._lock:
            freed = self._detach_all()
            self._active_id = None
        self._free(freed)

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

    def _detach(self, backend_id: str) -> str:
        """Drop one model from the bookkeeping, under the lock, and return its id."""
        if backend_id in self._resident:
            self._resident.remove(backend_id)
        if self._owned_id == backend_id:
            self._owned_id = None
        return backend_id

    def _detach_all(self, except_id: str | None = None) -> list[str]:
        owned = self._owned_id
        targets = list(self._resident)
        if owned is not None and owned not in targets:
            targets.append(owned)
        return [self._detach(one) for one in targets if one != except_id]

    def _detach_unretained(self, except_id: str) -> list[str]:
        owned = self._owned_id
        if owned is None or owned in self._resident or owned == except_id:
            return []
        return [self._detach(owned)]

    def _free(self, backend_ids: list[str], *, resident_credit: bool = True) -> list[str]:
        """Free the engines the caller detached, outside the lock.

        A model that will not free keeps owning its slot, so the next claim frees it
        before loading anything else. It is only recorded as resident when it holds
        memory that works: a runtime whose load failed must not count against the
        boundary, even if its cleanup also fails.
        """
        for backend_id in backend_ids:
            try:
                self._backends[backend_id].release()
            except Exception:
                # The caller detached this id, so recording it again is one entry, not two.
                with self._lock:
                    if resident_credit:
                        self._resident.append(backend_id)
                    self._owned_id = backend_id
                raise
        return backend_ids
