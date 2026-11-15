"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset

DEFAULT_MODEL = "Lightricks/LTX-2.5-Diffusers"


def storage_assets(config):
    return hub_asset(str(config.backend("ltx25_cuda").get("model", DEFAULT_MODEL)))
