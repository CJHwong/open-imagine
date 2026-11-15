"""Prepare each configured model once, then give it back."""

import time
from collections.abc import Callable, Sequence

from studio.l2_use_cases.boundaries.model_lifecycle_gateway import ModelLifecycleGateway


class PrepareModelsUseCase:
    """Load each model in turn and free it before the next one loads.

    A first load can build a pack of quantized weights or compile kernels for this
    machine, and a caller that would rather not pay for that inside a first generation
    runs this instead. A model is released even when its load fails, so one broken engine
    does not leave the memory of the others taken.
    """

    def execute(
        self,
        targets: Sequence[tuple[str, ModelLifecycleGateway]],
        on_start: Callable[[str], None] = lambda backend_id: None,
    ) -> list[tuple[str, float]]:
        """Prepare each target and report how long each one took, in order."""
        prepared: list[tuple[str, float]] = []
        for backend_id, model in targets:
            on_start(backend_id)
            started = time.monotonic()
            try:
                model.load()
            finally:
                model.release()
            prepared.append((backend_id, time.monotonic() - started))
        return prepared
