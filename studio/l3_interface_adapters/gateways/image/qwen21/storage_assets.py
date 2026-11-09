"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset


def storage_assets(config):
    return hub_asset("Qwen/Qwen-Image-2.1")
