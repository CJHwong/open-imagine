"""A run or a rewrite uses only a prepared model, so neither downloads nor packs one.

Every run claims its model before it loads it, so the claim is the one gate every
workspace passes. A rewrite claims nothing, so its rewriter carries the same check. A
prepare holds the ungated residency underneath, and so it is the only way in.
"""

from collections.abc import Callable

from studio.l1_entities.errors import ModelNotReady
from studio.l2_use_cases.boundaries.model_readiness_gateway import ModelReadinessGateway
from studio.l2_use_cases.boundaries.model_residency_gateway import ModelResidencyGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway


def require_ready(readiness: ModelReadinessGateway, backend_id: str) -> None:
    status = readiness.readiness(backend_id)
    if status.ready:
        return
    raise ModelNotReady(
        f"{backend_id} is not downloaded yet. Prepare it first: press Download on the page, "
        f'POST /api/v1/operations with {{"kind": "prepare", "backend": "{backend_id}"}}, '
        "or run `uv run studio --prepare`."
    )


class ReadyModelResidency(ModelResidencyGateway):
    def __init__(self, residency: ModelResidencyGateway, readiness: ModelReadinessGateway):
        self._residency = residency
        self._readiness = readiness

    def resident_gib(self, backend_id: str) -> float:
        return self._residency.resident_gib(backend_id)

    def select(self, backend_id: str) -> None:
        self._residency.select(backend_id)

    def claim(self, backend_id: str) -> tuple[str, ...]:
        require_ready(self._readiness, backend_id)
        return self._residency.claim(backend_id)

    def release_active(self) -> None:
        self._residency.release_active()

    def release_idle(self) -> None:
        self._residency.release_idle()

    def release(self) -> None:
        self._residency.release()


class ReadyPromptRewriter(PromptRewriterGateway):
    """Refuse a rewrite for a model whose selection, its rewriter included, is not prepared."""

    def __init__(self, rewriter: PromptRewriterGateway, readiness: ModelReadinessGateway, active_id: Callable[[], str]):
        self._rewriter = rewriter
        self._readiness = readiness
        self._active_id = active_id

    def modes(self):
        return self._rewriter.modes()

    def rewrite(self, prompt, mode, references, on_writing, should_stop):
        require_ready(self._readiness, self._active_id())
        return self._rewriter.rewrite(prompt, mode, references, on_writing, should_stop)

    def release(self) -> None:
        self._rewriter.release()

    def prepare(self) -> None:
        self._rewriter.prepare()
