"""Report the selected built-in rewriter's cache status without loading it."""

from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter import cache_line
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.model_factories.registry import IMAGE_REWRITER_FACTORIES
from studio.l4_frameworks_and_drivers.model_factories.rewriters import qwen21_rewrite_models


def rewriter_cache_line(config: Config) -> str:
    """What the page's rewriters will have to fetch, or "" when it has none.

    The line belongs beside the loading one, before the click rather than during
    it: the first rewrite in a mode fetches about 19 GB with the terminal kept
    quiet, so the button looks merely busy for minutes.
    """
    backend_id = config.default_backend
    models = qwen21_rewrite_models(config, backend_id) if backend_id in IMAGE_REWRITER_FACTORIES else None
    return cache_line(models) if models else ""
