"""Composition factory for image/viggle_turbo."""

from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.image.viggle_turbo.viggle_turbo_backend_gateway import (
    ViggleTurboBackendGateway,
)
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.lora_table import lora_files
from studio.l4_frameworks_and_drivers.model_factories.configuration import badge, offering


def viggle_turbo_backend(config: Config) -> ViggleTurboBackendGateway:
    """The two models qwen21 drives, built with Viggle's adapter and its schedule.

    The generator is told to sample the turbo schedule, which its command accepts.
    The edit half cannot be told, so its gateway supplies the schedule another way.

    The adapter's file is checked when this backend loads, not here. A backend is
    built whether or not it is used, and the stub builds every one of them, so a
    check here would stop page work on a machine that never asked for the model.
    """
    settings = config.backend("viggle_turbo")
    lora_path = config.required("viggle_turbo", "lora_path")
    quantize = settings.get("quantize")
    loras = lora_files(config, "viggle_turbo")
    return offering(
        ViggleTurboBackendGateway(
            Qwen21Generator(quantize, lora_path=lora_path, scheduler="viggle_turbo", lora_files=loras),
            Qwen21Edit(quantize, lora_path=lora_path, lora_files=loras),
            badge=badge(quantize),
            lora_path=lora_path,
            loras=loras,
        ),
        "viggle_turbo",
    )
