"""HyperFlow H3 Flash: the H3 gateway on the Flash pack, with six forwards and no guidance."""

from studio.l3_interface_adapters.gateways.video.minimax_h3.capabilities import FLASH
from studio.l3_interface_adapters.gateways.video.minimax_h3.minimax_h3_backend_gateway import MinimaxH3BackendGateway


class MinimaxH3FlashBackendGateway(MinimaxH3BackendGateway):
    def __init__(self, context):
        super().__init__(context, FLASH)
