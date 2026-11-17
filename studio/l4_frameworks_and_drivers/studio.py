"""The assembled Studio application and its owned lifecycle."""

import time
from collections.abc import Callable
from dataclasses import dataclass

from studio.l1_entities.errors import BackendBusy
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.cancel_run_use_case import CancelRunUseCase
from studio.l3_interface_adapters.gateways.in_memory.backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory.model_residency_gateway import InMemoryModelResidencyGateway
from studio.l3_interface_adapters.gateways.in_memory.operation_gateway import InMemoryOperationGateway
from studio.l3_interface_adapters.gateways.in_memory.video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from studio.l4_frameworks_and_drivers.connect import ConnectStatus, ConnectTransport

# How long a shutdown waits for the run it stopped to report its end. The video runner
# looks at the cancel flag four times a second, and a child killed on it returns at once.
SHUTDOWN_WAIT_SECONDS = 5.0
SHUTDOWN_POLL_SECONDS = 0.05


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
    close_gpu: Callable[[], None] | None = None

    def active_capabilities(self):
        return self.catalog.get(self.catalog.active_id()).capabilities()

    def start_connect(self) -> ConnectStatus | None:
        """Start the phone listener, if one is configured.

        A preflight failure raises, so an enabled connection that cannot run stops
        the studio instead of leaving the feature on but broken.
        """
        if self.connect is None:
            return None
        self.connect.preflight()
        return self.connect.start()

    def expire(self) -> None:
        self.operations.expire()

    def shutdown(self) -> None:
        """Stop the run in flight, free the one resident model, and close the server.

        The frees wait in line on the GPU thread, behind any run, so the run is
        cancelled first. Without that, Ctrl-C waited for the image to finish.
        """
        cleanups = [self._stop_run, self.cancel.execute, self.residency.release]
        cleanups.extend(model.release for model in (self.rewriter, self.video_rewriter) if model is not None)
        if self.connect is not None:
            cleanups.append(self.connect.stop)
        cleanups.append(self.operations.close)
        if self.close_gpu is not None:
            cleanups.append(self.close_gpu)
        failures = []
        for cleanup in cleanups:
            try:
                cleanup()
            except Exception as error:
                failures.append(error)
        if len(failures) == 1:
            raise failures[0]
        if failures:
            raise ExceptionGroup("Studio shutdown failed", failures)

    def _stop_run(self) -> None:
        """Mark the run in flight stopping, and give it a moment to end.

        `cancel.execute` sets the flag the image and voice engines read, and refuses a
        video on purpose: a public caller has to name its own render. Shutdown is not a
        caller, so it moves the active operation to stopping, which every kind reads. The
        wait is what stops an MLX video child outliving this process: its release is a
        no-op, and nothing else would wait for the kill to land.
        """
        active = self.operations.active()
        if active is None or active.get("status") not in ("running", "stopping"):
            return
        try:
            self.operations.stopping(active["id"])
        except BackendBusy:
            return  # it ended between the read and the stop
        end = time.monotonic() + SHUTDOWN_WAIT_SECONDS
        while self.operations.active() is not None:
            if time.monotonic() >= end:
                return
            time.sleep(SHUTDOWN_POLL_SECONDS)
