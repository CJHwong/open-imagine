"""Prepare one model's whole selection: its engine and its prompt rewriter.

A first load downloads the weights, builds any pack and compiles kernels for this
machine. A run never does that, so this is where it happens: as an operation of its own,
holding the GPU like a run, and recorded once it has proved every file is present.
"""

import threading
from collections.abc import Callable, Mapping

from studio.l1_entities.errors import BackendBusy, Cancelled, UnknownBackend
from studio.l1_entities.model_readiness import ModelReadiness
from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway
from studio.l2_use_cases.boundaries.model_readiness_gateway import ModelReadinessGateway
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway

ENGINE = "engine"
REWRITER = "rewriter"


class PrepareModelUseCase:
    """Load the engine, free it, then load the rewriter, and record the model as ready.

    The engine and its rewriter do not fit in memory together, so the engine goes before
    the rewriter loads. A stop lands between the two, never inside one, because a load is
    one blocking call: the same contract a rewrite keeps.
    """

    def __init__(
        self,
        engine_lock: threading.Lock,
        residency: ModelResidencyGateway,
        models: Mapping[str, ModelLifecycleGateway],
        rewriters: Mapping[str, PromptRewriterGateway],
        readiness: ModelReadinessGateway,
    ):
        self._engine_lock = engine_lock
        self._residency = residency
        self._models = models
        self._rewriters = rewriters
        self._readiness = readiness

    def execute(
        self,
        backend_id: str,
        on_stage: Callable[[str], None] = lambda stage: None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> ModelReadiness:
        model = self._models.get(backend_id)
        if model is None:
            raise UnknownBackend(f"No model is offered under the id {backend_id!r}.")
        if not self._engine_lock.acquire(blocking=False):
            raise BackendBusy("The model is busy. Wait for it, or cancel the active operation.")
        try:
            self._stop_if_asked(should_stop)
            on_stage(ENGINE)
            self._residency.claim(backend_id)
            try:
                model.prepare()
            finally:
                self._residency.release_active()
            rewriter = self._rewriters.get(backend_id)
            if rewriter is not None:
                self._stop_if_asked(should_stop)
                on_stage(REWRITER)
                rewriter.prepare()
            self._readiness.mark_prepared(backend_id)
            return self._readiness.readiness(backend_id)
        finally:
            self._engine_lock.release()

    @staticmethod
    def _stop_if_asked(should_stop: Callable[[], bool]) -> None:
        if should_stop():
            raise Cancelled("The prepare was cancelled.")
