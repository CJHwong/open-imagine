"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset


def storage_assets(config):
    return configured_asset(config, "minimax_h3", "model_dir", "Weights") + configured_asset(
        config, "minimax_h3", "engine_dir", "Runtime", kind="runtime"
    )
