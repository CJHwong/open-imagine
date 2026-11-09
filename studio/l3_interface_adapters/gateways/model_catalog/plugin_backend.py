"""Construct a normalized installed provider lazily."""

from studio.l3_interface_adapters.gateways.model_registration.registered_model_provider import registered_model_provider


def plugin_backend(plugins, kind, name, config, stub=False, enhanced_prompt=None, *, execute_process, services=None):
    provider = registered_model_provider(plugins, kind, name, execute_process)
    return provider.create(
        config, stub=stub, enhanced_prompt=enhanced_prompt, execute_process=execute_process, services=services
    )
