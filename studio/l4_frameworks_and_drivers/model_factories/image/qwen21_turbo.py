"""Composition factory for image/qwen21_turbo."""

from functools import partial

from studio.l3_interface_adapters.gateways.image.qwen21_turbo.official_qwen_turbo_backend_gateway import (
    OfficialQwenTurboBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.image.shared import qwen21_turbo_schedule
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.lora_table import lora_files
from studio.l4_frameworks_and_drivers.model_factories.configuration import badge, offering


def qwen21_turbo_backend(config: Config) -> OfficialQwenTurboBackendGateway:
    """The official Turbo checkpoint, which samples the sigma table it ships.

    The generator is told the schedule by name, and the gateway registers it when a
    run starts. Not here: building a backend must not import mflux, because the stub
    builds every backend on machines that cannot run a model at all, and its whole
    point is that the page still works there.
    """
    settings = config.backend("qwen21_turbo")
    from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit_input_cache import cache_edit_inputs
    from studio.l3_interface_adapters.gateways.image.qwen_runtime.encoder_restore import restore_text_encoder
    from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import active_mlx_memory

    model_dir = config.required("qwen21_turbo", "model_dir")
    quantize = settings.get("quantize")
    loras = lora_files(config, "qwen21_turbo")
    return offering(
        OfficialQwenTurboBackendGateway(
            Qwen21Generator(
                quantize,
                model_path=model_dir,
                scheduler=qwen21_turbo_schedule.SCHEDULER_NAME,
                restore_encoder=partial(restore_text_encoder, model_path=model_dir, quantize=quantize),
                lora_files=loras,
            ),
            Qwen21Edit(quantize, model_path=model_dir, prepare_model=cache_edit_inputs, lora_files=loras),
            badge=badge(quantize),
            model_dir=model_dir,
            memory_scope=active_mlx_memory,
            loras=loras,
        ),
        "qwen21_turbo",
    )
