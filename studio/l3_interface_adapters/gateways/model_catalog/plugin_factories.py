"""Bind installed registration IDs to lazy backend factories."""

from functools import partial

from studio.l3_interface_adapters.gateways.model_catalog.plugin_backend import plugin_backend
from studio.l3_interface_adapters.gateways.model_registration.installed_model_catalog import InstalledModelCatalog


def plugin_factories(
    plugins: InstalledModelCatalog | None, kind: str, stub: bool, execute_process, services=None
) -> dict:
    """One factory per installed model. A factory imports its plugin only when it is called,
    so a hidden model's code is never imported."""
    return (
        {
            name: partial(
                plugin_backend, plugins, kind, name, stub=stub, execute_process=execute_process, services=services
            )
            for name in plugins.ids(kind)
        }
        if plugins
        else {}
    )
