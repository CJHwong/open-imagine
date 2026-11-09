"""Composition factory for image/flux2."""

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.flux2.flux2_backend_gateway import Flux2BackendGateway
from studio.l3_interface_adapters.gateways.image.flux2.klein_models import KleinModels
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import reject_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.offering import badge


def flux2_backend(config: ModelConfigurationGateway, **_) -> Flux2BackendGateway:
    quantize = config.backend("flux2").get("quantize")
    reject_lora_tables(config.backend("flux2"), "flux2")
    return Flux2BackendGateway(KleinModels(config.required("flux2", "model_dir"), quantize), badge=badge(quantize))


PROVIDER = ModelProvider("flux2", "image", flux2_backend)
