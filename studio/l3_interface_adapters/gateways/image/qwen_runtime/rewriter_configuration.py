"""Qwen rewriter settings and cache reporting, shared by its checkpoints."""

from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter import Qwen21Rewriter, cache_line
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway

REWRITE_QUANTIZE_BITS = (0, 2, 3, 4, 5, 6, 8)


def qwen21_rewrite_models(config: ModelConfigurationGateway, backend_id: str) -> dict | None:
    """One rewriter model per mode: the text one rewrites a request, the image one
    reads the picture an edit will be of.

    Read from the section of the backend that will use it, since that is where a
    reader would look for it. None when studio.toml names neither. A settings file
    written before the rewriters existed has no keys for them, and that studio
    starts as it did, with no toggle, rather than refusing to boot.

    `rewrite_generate_local` and `rewrite_edit_local` name a converted checkpoint
    on disk. When that directory exists it is used instead of the repo id, which
    stays as the fallback for a machine that has not converted one.
    """
    settings = config.backend(backend_id)
    models = {
        "generate": settings.get("rewrite_generate_model"),
        "edit": settings.get("rewrite_edit_model"),
    }
    # A converted checkpoint is a local directory, and it answers first when it is
    # there. The repo id stays in the map for a machine that does not hold one, so a
    # fresh install still downloads and quantizes the bf16 card as it always did.
    for mode in ("generate", "edit"):
        local = settings.get(f"rewrite_{mode}_local")
        if local and Path(str(local)).expanduser().is_dir():
            models[mode] = str(Path(str(local)).expanduser())
    return models if all(models.values()) else None


def rewrite_quantize(config: ModelConfigurationGateway, backend_id: str) -> int:
    quantize = config.backend(backend_id).get("rewrite_quantize", 0)
    # bool is an int in Python: `false` equals 0 and would pass as full precision.
    if isinstance(quantize, bool) or quantize not in REWRITE_QUANTIZE_BITS:
        raise ModelConfigurationError(
            f"rewrite_quantize under [{backend_id}] must be 0, 2, 3, 4, 5, 6 or 8, not {quantize!r}"
        )
    return quantize


def build_rewriter(config: ModelConfigurationGateway, backend_id: str, **_):
    models = qwen21_rewrite_models(config, backend_id)
    quantize = rewrite_quantize(config, backend_id)
    return Qwen21Rewriter(models, quantize=quantize) if models else NoPromptRewriterGateway()


def rewriter_cache(config: ModelConfigurationGateway, backend_id: str) -> str:
    models = qwen21_rewrite_models(config, backend_id)
    return cache_line(models) if models else ""
