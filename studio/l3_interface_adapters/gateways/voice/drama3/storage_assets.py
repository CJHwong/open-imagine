"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset, runtime_asset


def storage_assets(config):
    return hub_asset("mlx-community/fish-audio-drama-3-8bit") + runtime_asset(config, "drama3")
