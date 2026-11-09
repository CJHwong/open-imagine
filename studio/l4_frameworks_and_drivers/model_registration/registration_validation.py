"""Explicit registry of supported model-registration validators."""

from studio.l4_frameworks_and_drivers.model_registration.gateway_registration_validation import (
    validate as validate_gateway,
)
from studio.l4_frameworks_and_drivers.model_registration.ltx_checkpoint_validation import validate as validate_ltx
from studio.l4_frameworks_and_drivers.model_registration.qwen_checkpoint_validation import validate as validate_qwen
from studio.plugins import GatewayModelRegistration
from studio.plugins.ltx_checkpoint_registration import LtxCheckpointRegistration
from studio.plugins.qwen_checkpoint_registration import QwenCheckpointRegistration

VALIDATORS = {
    LtxCheckpointRegistration: validate_ltx,
    QwenCheckpointRegistration: validate_qwen,
    GatewayModelRegistration: validate_gateway,
}


def validate_registration(registration, kind: str, name: str) -> None:
    # The gateway validator also gives malformed declarations the public contract error.
    validator = next(
        (validate for cls, validate in VALIDATORS.items() if isinstance(registration, cls)), validate_gateway
    )
    validator(registration, kind, name)
