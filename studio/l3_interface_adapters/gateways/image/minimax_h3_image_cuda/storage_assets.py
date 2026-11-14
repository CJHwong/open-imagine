"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset

DEFAULT_MODEL = "MiniMaxAI/MiniMax-H3-Image"


def storage_assets(config):
    return hub_asset(str(config.backend("minimax_h3_image_cuda").get("model", DEFAULT_MODEL)))
