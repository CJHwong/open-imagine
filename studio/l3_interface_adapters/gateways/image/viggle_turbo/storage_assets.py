"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset, hub_asset


def storage_assets(config):
    return hub_asset("Qwen/Qwen-Image-2.1") + configured_asset(
        config, "viggle_turbo", "lora_path", "Distillation weights"
    )
