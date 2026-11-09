"""Composition factory for image/krea2."""

from studio.l3_interface_adapters.gateways.image.krea2.krea2_backend_gateway import Krea2BackendGateway
from studio.l3_interface_adapters.gateways.image.krea2.krea2_model import Krea2Model
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.lora_table import no_loras


def krea2_backend(config: Config) -> Krea2BackendGateway:
    """Krea 2 Turbo from weights stored at int8. mflux runs the stored bits whatever it is
    asked for, so a quantize other than 8 is refused rather than shown and then ignored."""
    no_loras(config, "krea2")
    settings = config.backend("krea2")
    if "quantize" in settings and settings["quantize"] != 8:
        raise ConfigError("[krea2] runs its weights at int8, as they are stored. Remove its quantize, or use 8.")
    return Krea2BackendGateway(Krea2Model(config.required("krea2", "model_dir")))
