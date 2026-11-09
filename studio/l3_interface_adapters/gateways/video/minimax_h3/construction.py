"""Construct the built-in H3 integration without starting its worker."""

from types import MappingProxyType

from studio.l2_use_cases.model_factory_context import ModelFactoryContext
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.video.minimax_h3.capabilities import CAPABILITIES
from studio.l3_interface_adapters.gateways.video.minimax_h3.memory_estimate import estimate_peak_gib
from studio.l3_interface_adapters.gateways.video.minimax_h3.minimax_h3_backend_gateway import MinimaxH3BackendGateway

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


def memory_estimator(config):
    return estimate_peak_gib


PROVIDER = ModelProvider("minimax_h3", "video", minimax_h3_backend, estimator=memory_estimator)
