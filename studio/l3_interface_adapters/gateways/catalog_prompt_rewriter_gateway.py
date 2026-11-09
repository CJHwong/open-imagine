"""CatalogPromptRewriterGateway: one concrete prompt-rewriter implementation."""

from collections.abc import Callable, Mapping

from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.video_backend_catalog_gateway import VideoBackendCatalogGateway
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway


class CatalogPromptRewriterGateway(PromptRewriterGateway):
    """The rewriter of whichever backend the page is on.

    A rewriter belongs to a backend, and the page may switch backends, so the
    one in force has to follow the catalog. `release` frees every backend's
    rewriter, because the caller asking for memory wants all of it.
    """

    def __init__(
        self,
        rewriters: Mapping[str, PromptRewriterGateway],
        catalog: BackendCatalogGateway | VideoBackendCatalogGateway,
    ):
        self._rewriters = dict(rewriters)
        self._catalog = catalog
        self._none = NoPromptRewriterGateway()

    def modes(self) -> tuple[str, ...]:
        return self._active().modes()

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        return self._active().rewrite(prompt, mode, references, on_writing, should_stop)

    def release(self) -> None:
        for rewriter in self._rewriters.values():
            rewriter.release()

    def _active(self) -> PromptRewriterGateway:
        return self._rewriters.get(self._catalog.active_id(), self._none)
