"""NoPromptRewriterGateway: one concrete prompt-rewriter implementation."""

from collections.abc import Callable

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway


class NoPromptRewriterGateway(PromptRewriterGateway):
    """A backend with no rewriter. Its empty mode list hides the page's toggle,
    so `rewrite` is reached only by a caller that ignored the list."""

    def modes(self) -> tuple[str, ...]:
        return ()

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        raise InvalidJob("This backend has no prompt rewriter.")

    def release(self) -> None:
        pass
