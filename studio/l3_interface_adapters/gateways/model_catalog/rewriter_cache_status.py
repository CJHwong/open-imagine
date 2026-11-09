"""Report the selected model's declared rewriter cache without loading weights."""

from studio.l3_interface_adapters.gateways.model_catalog.registry import provider_for


def rewriter_cache_line(config) -> str:
    provider = provider_for("image", config.default_backend)
    return (
        provider.rewriter_cache(config, provider.backend_id) if provider is not None and provider.rewriter_cache else ""
    )
