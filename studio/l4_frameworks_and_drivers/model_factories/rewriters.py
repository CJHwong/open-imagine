"""Compose rewriters and their validated runtime settings."""

from pathlib import Path

from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter import Qwen21Rewriter
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.model_factories.registry import IMAGE_REWRITER_FACTORIES
from studio.l4_frameworks_and_drivers.model_registration.installed_model_catalog import InstalledModelCatalog
from studio.l4_frameworks_and_drivers.model_registration.model_backend_factory import ModelBackendFactory
from studio.plugins.qwen_checkpoint_registration import QwenCheckpointRegistration

REWRITE_QUANTIZE_BITS = (0, 2, 3, 4, 5, 6, 8)


def qwen21_rewrite_models(config: Config, backend_id: str) -> dict | None:
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


def rewrite_quantize(config: Config, backend_id: str) -> int:
    quantize = config.backend(backend_id).get("rewrite_quantize", 0)
    # bool is an int in Python: `false` equals 0 and would pass as full precision.
    if isinstance(quantize, bool) or quantize not in REWRITE_QUANTIZE_BITS:
        raise ConfigError(f"rewrite_quantize under [{backend_id}] must be 0, 2, 3, 4, 5, 6 or 8, not {quantize!r}")
    return quantize


def build_rewriters(config: Config, plugins: InstalledModelCatalog | None = None, stub: bool = False) -> dict:
    built = {}
    for backend_id in config.visible_backends:
        # A checkpoint runs on the Qwen engine, so it takes the Qwen rewriters as well.
        checkpoint = (
            plugins is not None
            and backend_id in plugins.ids("image")
            and isinstance(plugins.declaration("image", backend_id), QwenCheckpointRegistration)
        )
        if plugins and backend_id in plugins.ids("image") and not checkpoint:
            built[backend_id] = ModelBackendFactory(plugins).rewriter("image", backend_id, config, stub)
        else:
            rewriter = Qwen21Rewriter if checkpoint else IMAGE_REWRITER_FACTORIES.get(backend_id)
            models = qwen21_rewrite_models(config, backend_id) if rewriter else None
            quantize = rewrite_quantize(config, backend_id)
            built[backend_id] = (
                rewriter(models, quantize=quantize) if rewriter and models else NoPromptRewriterGateway()
            )
    return built
