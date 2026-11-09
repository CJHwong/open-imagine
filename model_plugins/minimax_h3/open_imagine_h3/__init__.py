"""Declare H3 without importing its engine or loading weights."""

from studio.plugins import GatewayModelRegistration

from .capabilities import CAPABILITIES
from .minimax_h3_backend_gateway import MinimaxH3BackendGateway

plugin = GatewayModelRegistration(CAPABILITIES, MinimaxH3BackendGateway, loras=True)
