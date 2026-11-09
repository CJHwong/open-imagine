"""Composition factory for image/qwen21."""

from studio.l3_interface_adapters.gateways.image.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.lora_table import lora_files
from studio.l4_frameworks_and_drivers.model_factories.configuration import badge, offering


def qwen21_backend(config: Config) -> Qwen21BackendGateway:
    quantize = config.backend("qwen21").get("quantize")
    loras = lora_files(config, "qwen21")
    return offering(
        Qwen21BackendGateway(
            Qwen21Generator(quantize, lora_files=loras),
            Qwen21Edit(quantize, lora_files=loras),
            badge=badge(quantize),
            loras=loras,
        ),
        "qwen21",
    )
