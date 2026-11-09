"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset, hub_asset


def storage_assets(config):
    model = str(config.backend("mlx_video").get("model_ltx23", ""))
    if not model:
        return ()
    if model.startswith(("/", "~", ".")):
        return configured_asset(config, "mlx_video", "model_ltx23", "Weights")
    return hub_asset(model)
