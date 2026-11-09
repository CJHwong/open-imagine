"""Storage owned by this model integration."""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset, runtime_asset


def storage_assets(config):
    return (
        configured_asset(config, "yue2", "model_dir", "Weights")
        + configured_asset(config, "yue2", "vae_dir", "Audio decoder")
        + configured_asset(config, "yue2", "transcription_cache_dir", "Transcription")
        + runtime_asset(config, "yue2")
    )
