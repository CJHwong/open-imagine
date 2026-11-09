"""The declarations an installed model entry point can export."""

from studio.plugins.gateway_model_registration import GatewayModelRegistration
from studio.plugins.ltx_checkpoint_registration import LtxCheckpointRegistration
from studio.plugins.qwen_checkpoint_registration import QwenCheckpointRegistration

ModelRegistration = GatewayModelRegistration | LtxCheckpointRegistration | QwenCheckpointRegistration
