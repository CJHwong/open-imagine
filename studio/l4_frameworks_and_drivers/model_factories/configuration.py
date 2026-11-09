"""Shared precision labels and startup capability validation."""

from studio.l1_entities.errors import StudioError
from studio.l4_frameworks_and_drivers.config import ConfigError


def badge(quantize: int | None) -> str:
    return f"int{quantize}" if quantize else "bf16"


def offering(gateway, backend_id: str):
    """The gateway, once its record took the LoRA table. A table that names a mode the
    model lacks fails at start, with the section to look in."""
    try:
        gateway.capabilities()
    except StudioError as error:
        raise ConfigError(f"[{backend_id}]: {error}") from None
    return gateway
