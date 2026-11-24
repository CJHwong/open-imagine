"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset

DEFAULT_MODEL = "MiniMaxAI/MiniMax-H3"
# The child pins this repository's revision. Flash reads the encoder and the VAEs of DEFAULT_MODEL.
FLASH_MODEL = "VideoRebirthAI/hyperflow-h3-flash"


def storage_assets(config):
    return hub_asset(str(config.backend("minimax_h3_cuda").get("model", DEFAULT_MODEL)))


def flash_storage_assets(config):
    """Flash owns only its two transformers. The text encoder and the VAEs belong to base H3."""
    return hub_asset(FLASH_MODEL)
