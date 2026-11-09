"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset


def storage_assets(config):
    return configured_asset(config, "qwen21_turbo", "model_dir", "Weights")
