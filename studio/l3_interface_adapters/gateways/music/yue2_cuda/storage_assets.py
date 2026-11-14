"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset

DEFAULT_MODEL = "m-a-p/YuE2-3B"


def storage_assets(config):
    return hub_asset(str(config.backend("yue2_cuda").get("model", DEFAULT_MODEL)))
