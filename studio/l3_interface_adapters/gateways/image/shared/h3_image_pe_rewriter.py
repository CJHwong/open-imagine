"""The MiniMax H3-Image prompt enhancer, driven as a resident script child.

The enhancer is a 27B model with its own dependency tree, so it runs beside the studio
rather than inside it. It stays loaded between presses of Rewrite and is released before an
image run, because the two do not fit in memory together.
"""

import base64
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild


def _no_progress(step: int, total: int) -> None:
    """The enhancer reports tokens, not a schedule a page can draw."""


class H3ImagePeRewriter(PromptRewriterGateway):
    def __init__(self, command: list[str]):
        self._child = StdioChild(command)

    def modes(self) -> tuple[str, ...]:
        return ("generate", "edit")

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        if mode not in self.modes():
            raise InvalidJob(f"The MiniMax H3-Image prompt enhancer does not serve {mode}.")
        if should_stop():
            raise Cancelled()
        job: dict[str, object] = {"kind": mode, "prompt": prompt}
        if mode == "edit":
            # The enhancer reads the pictures the run carries, and asks for no target ratio,
            # so the run keeps the shape its own size choice gives it.
            job["images"] = [base64.b64encode(reference.png).decode("ascii") for reference in references]
            job["ratio"] = "adaptive"
        self._child.wait_ready()
        on_writing()
        reply = self._child.request(job, _no_progress, should_stop)
        if reply.get("error"):
            raise InvalidJob(str(reply["error"]))
        return PromptRewrite(str(reply["prompt"]), reply.get("ratio") or None)

    def release(self) -> None:
        self._child.stop()
