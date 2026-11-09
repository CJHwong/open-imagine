"""Resolve immutable settings and the host process driver for a backend factory."""

from types import MappingProxyType

from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner
from studio.plugins.model_factory_context import ModelFactoryContext


def create_context(config: Config, name: str) -> ModelFactoryContext:
    return ModelFactoryContext(MappingProxyType(config.backend(name)), SubprocessRunner().execute)
