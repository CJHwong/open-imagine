"""Compose JSON adapters explicitly, as the production composition root does."""

from studio.l2_use_cases.complete_operation_use_case import CompleteOperationUseCase
from studio.l2_use_cases.prepare_batch_use_case import PrepareBatchUseCase
from studio.l3_interface_adapters.api.json_api import JsonApi
from studio.l3_interface_adapters.gateways.in_memory.operation_gateway import InMemoryOperationGateway


def api_for(
    controller,
    video=None,
    voice=None,
    music=None,
    memory_status=None,
    max_queue=0,
    resource_admission=None,
):
    operations = InMemoryOperationGateway(max_queue=max_queue)
    return JsonApi(
        controller,
        video,
        voice,
        music=music,
        operations=operations,
        completion=CompleteOperationUseCase(operations),
        batches=PrepareBatchUseCase(),
        memory_status=memory_status,
        resource_admission=resource_admission,
    )
