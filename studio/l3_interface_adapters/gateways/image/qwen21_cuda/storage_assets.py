"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset

DEFAULT_MODEL = "Qwen/Qwen-Image-2.1-Turbo"


def storage_assets(config):
    return hub_asset(str(config.backend("qwen21_turbo_cuda").get("model", DEFAULT_MODEL)))
