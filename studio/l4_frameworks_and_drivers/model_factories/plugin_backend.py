"""Select the host factory for a model registration."""

from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.model_factories.image.qwen_checkpoint import qwen_checkpoint_backend
from studio.l4_frameworks_and_drivers.model_factories.video.ltx_checkpoint import ltx_pack_backend
from studio.l4_frameworks_and_drivers.model_registration.installed_model_catalog import InstalledModelCatalog
from studio.l4_frameworks_and_drivers.model_registration.model_backend_factory import ModelBackendFactory
from studio.plugins.ltx_checkpoint_registration import LtxCheckpointRegistration
from studio.plugins.qwen_checkpoint_registration import QwenCheckpointRegistration


def plugin_backend(
    plugins: InstalledModelCatalog, kind: str, name: str, config: Config, stub: bool = False, enhanced_prompt=None
):
    """A plugin's model. An LTX pack or a Qwen checkpoint is built here, as the built-in models
    are, also for the stub: building it loads nothing. Every other plugin builds its own."""
    registration = plugins.declaration(kind, name)
    if isinstance(registration, LtxCheckpointRegistration):
        return ltx_pack_backend(config, registration, enhanced_prompt)
    if isinstance(registration, QwenCheckpointRegistration):
        return qwen_checkpoint_backend(config, registration)
    return ModelBackendFactory(plugins).build(kind, name, config, stub)
