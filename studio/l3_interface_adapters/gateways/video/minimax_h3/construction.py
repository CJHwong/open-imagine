"""Construct the built-in H3 integration without starting its worker."""

from types import MappingProxyType

from studio.l2_use_cases.model_factory_context import ModelFactoryContext
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.video.minimax_h3.capabilities import CAPABILITIES, FLASH_CAPABILITIES
from studio.l3_interface_adapters.gateways.video.minimax_h3.memory_estimate import estimate_peak_gib
from studio.l3_interface_adapters.gateways.video.minimax_h3.minimax_h3_backend_gateway import MinimaxH3BackendGateway
from studio.l3_interface_adapters.gateways.video.minimax_h3.minimax_h3_flash_backend_gateway import (
    MinimaxH3FlashBackendGateway,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3.storage_assets import flash_storage_assets, storage_assets

LORA_POLICY = LoraTablePolicy(mode_scoped=False)


def minimax_h3_backend(config, *, execute_process, **_):
    loras = parse_lora_tables(config.backend("minimax_h3"), "minimax_h3", policy=LORA_POLICY)
    return MinimaxH3BackendGateway(
        ModelFactoryContext(
            MappingProxyType(config.backend("minimax_h3")),
            execute_process,
            capabilities=loras.offer_video(CAPABILITIES),
            lora_paths=MappingProxyType({item.lora.id: item.path for item in loras.files}),
        )
    )


def minimax_h3_flash_backend(config, *, execute_process, **_):
    """Flash runs on the engine and the model folder of the [minimax_h3] section. It offers the
    LoRAs of that section's tables. They were trained on base H3, and none was tried on Flash."""
    loras = parse_lora_tables(config.backend("minimax_h3"), "minimax_h3", policy=LORA_POLICY)
    return MinimaxH3FlashBackendGateway(
        ModelFactoryContext(
            MappingProxyType(config.backend("minimax_h3")),
            execute_process,
            capabilities=loras.offer_video(FLASH_CAPABILITIES),
            lora_paths=MappingProxyType({item.lora.id: item.path for item in loras.files}),
        )
    )


def memory_estimator(config):
    return estimate_peak_gib


PROVIDER = ModelProvider(
    "minimax_h3",
    "video",
    minimax_h3_backend,
    estimator=memory_estimator,
    storage_assets=storage_assets,
    storage_name="MiniMax H3",
)

# Flash peaks lower than base H3, because it runs no guidance and drops three blocks: a spike on
# 2026-11-11 saw 26.9 GiB in the text encoder and 22.8 GiB in the denoise at 768 x 448 and 124
# frames. No run sampled the whole machine, so the gate keeps the base figure, which is higher.
FLASH_PROVIDER = ModelProvider(
    "minimax_h3_flash",
    "video",
    minimax_h3_flash_backend,
    estimator=memory_estimator,
    storage_assets=flash_storage_assets,
    storage_name="HyperFlow H3 Flash",
)
