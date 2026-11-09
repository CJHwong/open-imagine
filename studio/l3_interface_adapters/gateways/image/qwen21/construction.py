"""Composition factory for image/qwen21."""

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from studio.l3_interface_adapters.gateways.image.qwen21.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter_configuration import (
    build_rewriter,
    rewriter_cache,
)
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.model_configuration.offering import badge, offering

LORA_POLICY = LoraTablePolicy(mode_scoped=True)


def qwen21_backend(config: ModelConfigurationGateway, **_) -> Qwen21BackendGateway:
    quantize = config.backend("qwen21").get("quantize")
    loras = parse_lora_tables(config.backend("qwen21"), "qwen21", policy=LORA_POLICY)
    return offering(
        Qwen21BackendGateway(
            Qwen21Generator(quantize, lora_files=loras),
            Qwen21Edit(quantize, lora_files=loras),
            badge=badge(quantize),
            loras=loras,
        ),
        "qwen21",
    )


PROVIDER = ModelProvider(
    "qwen21",
    "image",
    qwen21_backend,
    rewriter=build_rewriter,
    rewriter_cache=rewriter_cache,
    storage_assets=storage_assets,
    storage_name="Qwen-Image-2.1",
)
