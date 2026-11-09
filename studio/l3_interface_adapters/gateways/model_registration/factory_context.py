"""Resolve immutable settings and the host process driver for a backend factory."""

from types import MappingProxyType

from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.boundaries.process_gateway import ProcessGateway
from studio.l2_use_cases.model_factory_context import ModelFactoryContext


def create_context(
    config: ModelConfigurationGateway, name: str, execute_process: ProcessGateway
) -> ModelFactoryContext:
    return ModelFactoryContext(MappingProxyType(config.backend(name)), execute_process)
