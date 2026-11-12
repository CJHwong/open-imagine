"""The assembled Studio application and its owned lifecycle."""

from dataclasses import dataclass

from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.cancel_run_use_case import CancelRunUseCase
from studio.l3_interface_adapters.gateways.in_memory.backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory.model_residency_gateway import InMemoryModelResidencyGateway
from studio.l3_interface_adapters.gateways.in_memory.operation_gateway import InMemoryOperationGateway
from studio.l3_interface_adapters.gateways.in_memory.video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from studio.l4_frameworks_and_drivers.connect import ConnectStatus, ConnectTransport


@dataclass(frozen=True)
class Studio:
    handler: type
    catalog: InMemoryBackendCatalogGateway
    video_catalog: InMemoryVideoBackendCatalogGateway | None
    residency: InMemoryModelResidencyGateway
    cancel: CancelRunUseCase
    operations: InMemoryOperationGateway
    rewriter: PromptRewriterGateway | None = None

    video_rewriter: PromptRewriterGateway | None = None

    connect: ConnectTransport | None = None

    def active_capabilities(self):
        return self.catalog.get(self.catalog.active_id()).capabilities()

    def start_connect(self) -> ConnectStatus | None:
        """Start the phone listener, if one is configured. A failure is reported in
        the status rather than stopping a studio that still serves this machine."""
        return None if self.connect is None else self.connect.start()

    def expire(self) -> None:
        self.operations.expire()

    def shutdown(self) -> None:
        """Free the one resident model and the prompt rewriter.

        The frees wait in line on the GPU thread, behind any run, so the run is
        cancelled first. Without that, Ctrl-C waited for the image to finish.
        """
        self.cancel.execute()
        self.residency.release()
        self.operations.close()
        if self.rewriter is not None:
            self.rewriter.release()
        if self.video_rewriter is not None:
            self.video_rewriter.release()
        if self.connect is not None:
            self.connect.stop()
