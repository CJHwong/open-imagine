"""Composition factory for image/flux3."""

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.boundaries.process_gateway import ProcessGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.flux3.flux3_backend_gateway import Flux3BackendGateway
from studio.l3_interface_adapters.gateways.image.flux3.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.model_configuration.offering import badge


def flux3_backend(config: ModelConfigurationGateway, *, execute_process: ProcessGateway, **_) -> Flux3BackendGateway:
    quantize = config.backend("flux3").get("quantize", 8)
    return Flux3BackendGateway(
        config.required("flux3", "model_dir"),
        config.required("flux3", "python_path"),
        quantize,
        badge=badge(quantize),
        execute_process=execute_process,
    )


PROVIDER = ModelProvider("flux3", "image", flux3_backend, storage_assets=storage_assets, storage_name="FLUX3")
