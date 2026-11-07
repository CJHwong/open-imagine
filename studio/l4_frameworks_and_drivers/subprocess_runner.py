"""Stream and stop one owned child; engine commands and interpretation are injected."""

import os
import re
import selectors
import signal
import subprocess
import time
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager, suppress
from typing import BinaryIO, cast

from studio.l1_entities.errors import Cancelled, StudioError


class SubprocessRunner:
    def execute(
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
    ) -> None:
        should_cancel = cancelled or (lambda: False)
        inherited = os.environ.copy()
        inherited.update(environment or {})
        with _owned_process(
            subprocess.Popen(
                command,
                stdin=subprocess.PIPE if input_bytes is not None else None,
                stdout=subprocess.PIPE if consume_output is not None else subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=inherited,
                start_new_session=terminate_group,
            ),
            terminate_group,
        ) as process:
            stderr = cast(BinaryIO, process.stderr)
            started = time.monotonic()
            recent: deque[str] = deque(maxlen=tail_lines)
            with selectors.DefaultSelector() as selector:
                selector.register(stderr, selectors.EVENT_READ, "stderr")
                if process.stdout is not None:
                    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                pending = memoryview(input_bytes or b"")
                if process.stdin is not None:
                    if pending:
                        os.set_blocking(process.stdin.fileno(), False)
                        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
                    else:
                        process.stdin.close()
                while selector.get_map() or process.poll() is None:
                    if timeout_started is not None:
                        item_started = timeout_started()
                        if item_started is not None:
                            started = item_started
                    if should_cancel():
                        raise Cancelled(cancel_message)
                    remaining = timeout_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        if not terminate_group:
                            process.kill()
                            process.wait()
                        raise StudioError(timeout_message)
                    if not selector.get_map():
                        time.sleep(min(0.05, remaining))
                        continue
                    for key, _ in selector.select(min(0.25, remaining)):
                        stream = cast(BinaryIO, key.fileobj)
                        if key.data == "stdin":
                            try:
                                pending = pending[os.write(stream.fileno(), pending[:65536]) :]
                            except BrokenPipeError:
                                pending = memoryview(b"")
                            if not pending:
                                selector.unregister(stream)
                                stream.close()
                            continue
                        chunk = os.read(stream.fileno(), 65536)
                        if not chunk:
                            selector.unregister(stream)
                            continue
                        if key.data == "stdout":
                            cast(Callable, consume_output)(chunk)
                        else:
                            text = chunk.decode(errors="replace")
                            recent.extend(line for line in re.split(r"[\r\n]+", text) if line.strip())
                            if consume:
                                consume(text)
            return_code = process.wait()
            if should_cancel():
                raise Cancelled(cancel_message)
            if return_code:
                raise StudioError(failure_message(return_code, recent))


@contextmanager
def _owned_process(process: subprocess.Popen, group: bool):
    with process:
        try:
            yield process
        finally:
            if group or process.poll() is None:
                _stop_process(process, group)


def _stop_process(process: subprocess.Popen, group: bool = False) -> None:
    if not group and process.poll() is not None:
        return
    try:
        if group:
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    finally:
        if group:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
