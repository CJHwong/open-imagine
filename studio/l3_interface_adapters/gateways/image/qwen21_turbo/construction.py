"""Composition factory for image/qwen21_turbo."""

from functools import partial

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.memory_estimate import (
    QWEN_TURBO_WEIGHTS_GIB,
    estimate_peak_gib,
)
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.official_qwen_turbo_backend_gateway import (
    OfficialQwenTurboBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter_configuration import (
    build_rewriter,
    rewriter_cache,
)
from studio.l3_interface_adapters.gateways.image.shared import qwen21_turbo_schedule
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.model_configuration.offering import badge, offering

LORA_POLICY = LoraTablePolicy(mode_scoped=True)


def qwen21_turbo_backend(config: ModelConfigurationGateway, **_) -> OfficialQwenTurboBackendGateway:
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
    loras = parse_lora_tables(config.backend("qwen21_turbo"), "qwen21_turbo", policy=LORA_POLICY)
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


def memory_estimator(config):
    return partial(estimate_peak_gib, quantize=config.backend("qwen21_turbo").get("quantize"))


PROVIDER = ModelProvider(
    "qwen21_turbo",
    "image",
    qwen21_turbo_backend,
    estimator=memory_estimator,
    rewriter=build_rewriter,
    rewriter_cache=rewriter_cache,
    storage_assets=storage_assets,
    storage_name="Qwen Turbo",
    resident_gib=QWEN_TURBO_WEIGHTS_GIB,
)
