"""Storage owned by this model integration.

Both entries read the same repository, so each one resolves its own section and asks for the
same checkpoint. The NVFP4 entry also builds a pack from it, which is not a repository
download and is not declared here.
"""

from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import hub_asset

DEFAULT_MODEL = "m-a-p/YuE2-3B"


def storage_assets_for(backend_id: str):
    def assets(config):
        return hub_asset(str(config.backend(backend_id).get("model", DEFAULT_MODEL)))

    return assets


storage_assets = storage_assets_for("yue2_cuda")
