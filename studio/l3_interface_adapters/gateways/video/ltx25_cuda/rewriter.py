"""LTX-2.5's own prompt enhancer on CUDA, asked through the resident video child.

The enhancer is a component of the video pipeline, so it is in memory whenever the video model
is. A rewrite is one more request to that child, and freeing the video model frees the
enhancer with it. The child's docstring holds the precision and the measurement.
"""

import base64
import hashlib
from collections import OrderedDict
from collections.abc import Callable

from studio.l1_entities.errors import InvalidJob, StudioError
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

BACKEND_ID = "ltx25_cuda"


def _digest(prompt: str, references) -> str:
    """The prompt and the first keyframe, the one the enhancer reads, as one digest. The
    record keeps this and never the words, so a private caller's prompt leaves no copy."""
    digest = hashlib.sha256(prompt.encode("utf-8"))
    digest.update(b"\0" + (hashlib.sha256(references[0].png).digest() if references else b""))
    return digest.hexdigest()


class RewrittenPrompts:
    """The prompts the enhancer wrote, with the keyframe each was written for.

    A run whose prompt is one of them skips the enhancer, the same way the MLX path does:
    enhancing an enhanced prompt again would change the words the page showed. The record
    lives in memory only, holds digests rather than words, and keeps the latest prompts.
    """

    LIMIT = 128

    def __init__(self):
        self._written: OrderedDict[str, None] = OrderedDict()

    def add(self, prompt: str, references) -> None:
        self._written[_digest(prompt, references)] = None
        while len(self._written) > self.LIMIT:
            self._written.popitem(last=False)

    def wrote(self, prompt: str, references) -> bool:
        return _digest(prompt, references) in self._written


class Ltx25CudaRewriter(PromptRewriterGateway):
    def __init__(self, child: StdioChild, rewritten: RewrittenPrompts):
        self._child = child
        self._rewritten = rewritten

    def modes(self) -> tuple[str, ...]:
        return ("generate",)

    def resident_in(self) -> str | None:
        return BACKEND_ID

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        if mode != "generate":
            raise InvalidJob(f"The LTX-2.5 enhancer does not serve {mode}.")
        payload = {
            "task": "rewrite",
            "prompt": prompt,
            "references": [base64.b64encode(reference.png).decode("ascii") for reference in references[:1]],
        }
        # The child loads the video model before it answers, when it is not loaded yet,
        # and the caller cannot see that from here. The Qwen rewriter says the same.
        on_writing()
        reply = self._child.request(payload, lambda *_: None, should_stop)
        text = str(reply.get("text", "")).strip()
        if not text:
            raise StudioError("The LTX enhancer returned an empty prompt. Try rewriting again.")
        self._rewritten.add(text, references)
        return PromptRewrite(text)

    def release(self) -> None:
        # The enhancer belongs to the video model, and the studio frees that through the
        # video backend.
        pass
