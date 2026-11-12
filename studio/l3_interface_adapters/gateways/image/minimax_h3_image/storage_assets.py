"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset


def storage_assets(config):
    # The engine runs from the environment uv builds for the child script, so this model
    # owns weights only. uv caches that environment outside the model folder.
    return configured_asset(config, "minimax_h3_image", "model_dir", "Weights")
