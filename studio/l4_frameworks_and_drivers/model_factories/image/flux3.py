"""Composition factory for image/flux3."""

from studio.l3_interface_adapters.gateways.image.flux3.flux3_backend_gateway import Flux3BackendGateway
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.model_factories.configuration import badge
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner


def flux3_backend(config: Config) -> Flux3BackendGateway:
    quantize = config.backend("flux3").get("quantize", 8)
    return Flux3BackendGateway(
        config.required("flux3", "model_dir"),
        config.required("flux3", "python_path"),
        quantize,
        badge=badge(quantize),
        execute_process=SubprocessRunner().execute,
    )
