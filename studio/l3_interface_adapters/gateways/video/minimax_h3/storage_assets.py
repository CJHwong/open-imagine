"""Storage owned by this model integration."""

from pathlib import Path

from studio.l1_entities.model_asset import ModelAsset
from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset
from studio.l3_interface_adapters.gateways.video.minimax_h3.runtime import FLASH_PACK


def storage_assets(config):
    return configured_asset(config, "minimax_h3", "model_dir", "Weights") + configured_asset(
        config, "minimax_h3", "engine_dir", "Runtime", kind="runtime"
    )


def flash_storage_assets(config):
    """Flash owns only its transformer, a folder inside the model folder of base H3. The text
    encoder, the VAEs and the engine belong to base H3."""
    root = config.backend("minimax_h3").get("model_dir")
    return (ModelAsset("Weights", str(Path(str(root)) / FLASH_PACK)),) if root else ()
