"""Host-owned cancellable child-process execution."""

from collections.abc import Callable
from typing import Protocol


class ProcessGateway(Protocol):
    def __call__(
        self,
        command: list[str],
        cancelled: Callable[[], bool] | None = None,
        consume: Callable[[str], None] | None = None,
        timeout_started: Callable[[], float | None] | None = None,
        *,
        environment: dict[str, str] | None = None,
        timeout_seconds: float = 3600,
        timeout_message: str = "The child process timed out.",
        cancel_message: str = "The child process was cancelled.",
        failure_message: Callable,
        tail_lines: int = 12,
        input_bytes: bytes | None = None,
        consume_output: Callable[[bytes], None] | None = None,
        terminate_group: bool = False,
    ) -> None: ...
