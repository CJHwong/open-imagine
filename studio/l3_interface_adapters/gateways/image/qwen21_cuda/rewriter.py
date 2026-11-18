"""The Qwen prompt rewriters on the CUDA engine, through the cards the MLX path loads.

The same two cards, the same instructions, the same language nudge and the same answer
parsing: `qwen_runtime/rewriter_text` holds that contract and both engines import it. What
differs is the loader and the sampler, which run in the child.
"""

import base64
from collections.abc import Callable, Mapping

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter import cache_line
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter_text import (
    MAX_TOKENS,
    as_rewrite,
    in_the_request_language,
    smaller_png,
    system_prompt,
)
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

# The cards' own sampling, measured through the MLX path on 2026-09-27. The same numbers
# are sent to the CUDA card so one prompt gets the same treatment on either machine.
TEMPERATURE = 1.0
TOP_P = 0.95
TOP_K = 20

# `rewrite_quantize` is a width in bits, as it is for the MLX rewriter. This engine holds a
# card at full precision or in fp8; see the child's docstring for the measurement.
REWRITE_PRECISIONS = {0: "bf16", 8: "fp8"}

# The two modes the cards serve, and the setting each one reads.
MODEL_SETTINGS = {"generate": "rewrite_generate_model", "edit": "rewrite_edit_model"}


def rewrite_models(config: ModelConfigurationGateway, backend_id: str) -> dict | None:
    """One card per mode, or None when the section names neither."""
    settings = config.backend(backend_id)
    models = {mode: settings.get(key) for mode, key in MODEL_SETTINGS.items()}
    return {mode: str(repo) for mode, repo in models.items()} if all(models.values()) else None


class Qwen21CudaRewriter(PromptRewriterGateway):
    """The resident child, asked for one mode at a time."""

    def __init__(self, child: StdioChild, models: Mapping[str, str]):
        self._child = child
        self._models = dict(models)

    def modes(self) -> tuple[str, ...]:
        return tuple(self._models)

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        if mode not in self._models:
            raise InvalidJob(f"The Qwen prompt rewriter does not serve {mode}.")
        payload = {
            "role": mode,
            "system": system_prompt(self._models[mode]),
            "user": in_the_request_language(prompt),
            "references": [base64.b64encode(smaller_png(reference.png)).decode("ascii") for reference in references],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "top_k": TOP_K,
            # Off: the thinking block cost 25 seconds and the rewrite is one sentence.
            "enable_thinking": False,
        }
        # The child loads the card before it answers, and the caller cannot see that
        # from here. Saying it now is the same contract the MLX adapter keeps.
        on_writing()
        reply = self._child.request(payload, lambda *_: None, should_stop)
        if "error" in reply:
            raise InvalidJob(str(reply["error"]))
        return as_rewrite(str(reply.get("text", "")))

    def release(self) -> None:
        self._child.stop()


def rewrite_precision(config: ModelConfigurationGateway, backend_id: str) -> str:
    quantize = config.backend(backend_id).get("rewrite_quantize", 0)
    # bool is an int in Python: `false` equals 0 and would pass as full precision.
    if isinstance(quantize, bool) or quantize not in REWRITE_PRECISIONS:
        raise ModelConfigurationError(f"rewrite_quantize under [{backend_id}] must be 0 or 8, not {quantize!r}")
    return REWRITE_PRECISIONS[quantize]


def build_rewriter(config: ModelConfigurationGateway, backend_id: str, **_):
    models = rewrite_models(config, backend_id)
    if not models:
        return NoPromptRewriterGateway()
    from studio.l3_interface_adapters.gateways.image.qwen21_cuda.construction import rewriter_command

    command = rewriter_command(models, rewrite_precision(config, backend_id))
    return Qwen21CudaRewriter(StdioChild(command), models)


def rewriter_cache(config: ModelConfigurationGateway, backend_id: str) -> str:
    models = rewrite_models(config, backend_id)
    return cache_line(models) if models else ""
