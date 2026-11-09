"""Build rewriters through the selected model providers."""

from studio.l3_interface_adapters.gateways.model_catalog.composite_model_catalog_gateway import (
    CompositeModelCatalogGateway,
)
from studio.l3_interface_adapters.gateways.model_catalog.registry import BUILTIN_PROVIDERS
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stub.prompt_rewriter_gateway import StubPromptRewriterGateway


def build_rewriters(config, plugins=None, stub=False, *, execute_process, kind="image", names=None, services=None):
    catalog = CompositeModelCatalogGateway(BUILTIN_PROVIDERS, plugins, execute_process)
    built = {}
    for name in config.visible_backends if names is None else names:
        provider = catalog.provider(kind, name)
        if provider.rewriter is None:
            built[name] = NoPromptRewriterGateway()
        elif stub:
            built[name] = StubPromptRewriterGateway()
        else:
            built[name] = provider.rewriter(config, name, services=services)
    return built
