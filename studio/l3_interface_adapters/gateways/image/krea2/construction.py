"""Composition factory for image/krea2."""

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.krea2.krea2_backend_gateway import Krea2BackendGateway
from studio.l3_interface_adapters.gateways.image.krea2.krea2_model import Krea2Model
from studio.l3_interface_adapters.gateways.image.krea2.memory_estimate import estimate_peak_gib
from studio.l3_interface_adapters.gateways.image.krea2.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import reject_lora_tables


def krea2_backend(config: ModelConfigurationGateway, **_) -> Krea2BackendGateway:
    """Krea 2 Turbo from weights stored at int8. mflux runs the stored bits whatever it is
    asked for, so a quantize other than 8 is refused rather than shown and then ignored."""
    reject_lora_tables(config.backend("krea2"), "krea2")
    settings = config.backend("krea2")
    if "quantize" in settings and settings["quantize"] != 8:
        raise ModelConfigurationError(
            "[krea2] runs its weights at int8, as they are stored. Remove its quantize, or use 8."
        )
    return Krea2BackendGateway(Krea2Model(config.required("krea2", "model_dir")))


def memory_estimator(config):
    return estimate_peak_gib


PROVIDER = ModelProvider(
    "krea2", "image", krea2_backend, estimator=memory_estimator, storage_assets=storage_assets, storage_name="Krea 2"
)
