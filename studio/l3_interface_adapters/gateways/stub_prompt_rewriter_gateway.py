"""StubPromptRewriterGateway: one concrete prompt-rewriter implementation."""

import time
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway


class StubPromptRewriterGateway(PromptRewriterGateway):
    """The stub's rewriter: the page gets its toggle and its answer, and no model runs.

    It reports every mode the qwen21 rewriter serves, so a change to the page can
    be checked on a machine with no GPU.
    """

    MODES = ("generate", "edit")

    # The stub writes in slices, so a page check can watch both phases and stop the
    # middle of one. The real rewriter loads about 19 GB in the first phase and
    # writes for 22 to 32 seconds in the second, so the shape is the same and only
    # the clock is shorter. The preparing slice is long enough for a poll to see it.
    PREPARING_SECONDS = 1.2
    WRITING_SLICE_SECONDS = 0.6
    WRITING_SLICES = 5

    def modes(self) -> tuple[str, ...]:
        return self.MODES

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        time.sleep(self.PREPARING_SECONDS)
        # A stop cannot land during the load, here as on the real one. It is
        # remembered instead, and nothing is written after it.
        if should_stop():
            raise Cancelled("stopped while the stub got ready")
        on_writing()
        for _ in range(self.WRITING_SLICES):
            time.sleep(self.WRITING_SLICE_SECONDS)
            if should_stop():
                raise Cancelled("stopped while the stub wrote")
        return PromptRewrite(prompt=f"{prompt} A longer version of it, written for the stub.", ratio="3:2")

    def release(self) -> None:
        pass
