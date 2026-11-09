"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset


def storage_assets(config):
    return configured_asset(config, "krea2", "model_dir", "Weights")
