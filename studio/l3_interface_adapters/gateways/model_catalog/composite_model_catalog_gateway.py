"""Combine built-in providers with lazily translated external declarations."""

from studio.l2_use_cases.boundaries.model_catalog_gateway import ModelCatalogGateway
from studio.l3_interface_adapters.gateways.model_registration.registered_model_provider import registered_model_provider


class CompositeModelCatalogGateway(ModelCatalogGateway):
    def __init__(self, providers, installed, execute_process):
        self._providers = {(provider.kind, provider.backend_id): provider for provider in providers}
        self._installed = installed
        self._execute_process = execute_process

    def ids(self, kind):
        builtin = tuple(name for workspace, name in self._providers if workspace == kind)
        return builtin + (self._installed.ids(kind) if self._installed is not None and kind != "music" else ())

    def provider(self, kind, name):
        provider = self._providers.get((kind, name))
        if provider is not None:
            return provider
        return registered_model_provider(self._installed, kind, name, self._execute_process)
