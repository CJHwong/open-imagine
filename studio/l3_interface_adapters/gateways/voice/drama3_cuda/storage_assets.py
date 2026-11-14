"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset

DEFAULT_CHECKPOINT = "fishaudio/drama-3"


def storage_assets(config):
    return hub_asset(str(config.backend("drama3_cuda").get("checkpoint", DEFAULT_CHECKPOINT)))
