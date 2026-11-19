"""Prepare each configured model once, then give it back."""

import time
from collections.abc import Callable, Sequence

from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway
from studio.l2_use_cases.boundaries.model_readiness_gateway import ModelReadinessGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway

Target = tuple[str, ModelLifecycleGateway, PromptRewriterGateway | None]


class PrepareModelsUseCase:
    """Load each model and its prompt rewriter in turn, and free each before the next loads.

    A first load can download weights, build a pack of quantized weights or compile kernels
    for this machine, and a run never does that, so this command does it for every model at
    once. A model is released even when its load fails, so one broken engine does not leave
    the memory of the others taken. A model whose engine and rewriter both loaded is
    recorded as ready, the same record the page's Download writes.
    """

    def __init__(self, readiness: ModelReadinessGateway | None = None):
        self._readiness = readiness

    def execute(
        self,
        targets: Sequence[Target],
        on_start: Callable[[str], None] = lambda backend_id: None,
    ) -> list[tuple[str, float]]:
        """Prepare each target and report how long each one took, in order."""
        prepared: list[tuple[str, float]] = []
        for backend_id, model, rewriter in targets:
            on_start(backend_id)
            started = time.monotonic()
            _prepare_model(backend_id, model)
            if rewriter is not None:
                rewriter.prepare()
            if self._readiness is not None:
                self._readiness.mark_prepared(backend_id)
            prepared.append((backend_id, time.monotonic() - started))
        return prepared


def _prepare_model(backend_id: str, model: ModelLifecycleGateway) -> None:
    try:
        model.prepare()
    except BaseException as load_error:
        try:
            model.release()
        except BaseException as release_error:
            raise BaseExceptionGroup(f"{backend_id}: load and release failed", [load_error, release_error]) from None
        raise
    model.release()
