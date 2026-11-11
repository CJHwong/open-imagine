"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset, runtime_asset


def storage_assets(config):
    return configured_asset(config, "minimax_h3_image", "model_dir", "Weights") + runtime_asset(
        config, "minimax_h3_image"
    )
