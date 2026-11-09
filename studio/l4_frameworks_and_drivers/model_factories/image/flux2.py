"""Composition factory for image/flux2."""

from studio.l3_interface_adapters.gateways.image.flux2.flux2_backend_gateway import Flux2BackendGateway
from studio.l3_interface_adapters.gateways.image.flux2.klein_models import KleinModels
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.lora_table import no_loras
from studio.l4_frameworks_and_drivers.model_factories.configuration import badge


def flux2_backend(config: Config) -> Flux2BackendGateway:
    quantize = config.backend("flux2").get("quantize")
    no_loras(config, "flux2")
    return Flux2BackendGateway(KleinModels(config.required("flux2", "model_dir"), quantize), badge=badge(quantize))
