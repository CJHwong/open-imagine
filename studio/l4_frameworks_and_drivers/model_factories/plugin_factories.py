"""Bind installed registration IDs to lazy backend factories."""

from functools import partial

from studio.l4_frameworks_and_drivers.model_factories.plugin_backend import plugin_backend
from studio.l4_frameworks_and_drivers.model_registration.installed_model_catalog import InstalledModelCatalog


def plugin_factories(plugins: InstalledModelCatalog | None, kind: str, stub: bool) -> dict:
    """One factory per installed model. A factory imports its plugin only when it is called,
    so a hidden model's code is never imported."""
    return (
        {name: partial(plugin_backend, plugins, kind, name, stub=stub) for name in plugins.ids(kind)} if plugins else {}
    )
