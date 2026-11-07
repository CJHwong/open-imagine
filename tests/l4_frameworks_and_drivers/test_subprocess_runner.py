import subprocess
import sys
from typing import Any, cast

from studio.l4_frameworks_and_drivers.subprocess_runner import _stop_process


def test_stop_process_leaves_a_child_that_already_exited():
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()

    _stop_process(process)


def test_stop_process_ignores_a_process_that_is_already_gone():
    class Gone:
        def poll(self):
            return None

        def terminate(self):
            raise ProcessLookupError

    _stop_process(cast(Any, Gone()))


def test_stop_process_kills_a_child_that_ignores_terminate():
    class Stubborn:
        def __init__(self):
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("child", timeout)
            return 0

        def kill(self):
            self.killed = True

    child = Stubborn()

    _stop_process(cast(Any, child))

    assert child.killed is True


def test_generic_driver_streams_without_a_consumer_and_preserves_caller_environment(monkeypatch):
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    monkeypatch.setenv("STUDIO_TEST_CHILD_VALUE", "parent")
    command = [
        sys.executable,
        "-c",
        "import os,sys; sys.stderr.write(os.environ['STUDIO_TEST_CHILD_VALUE']); raise SystemExit(2)",
    ]
    import os

    import pytest

    from studio.l1_entities.errors import StudioError

    with pytest.raises(StudioError, match="2: child"):
        SubprocessRunner().execute(
            command,
            environment={"STUDIO_TEST_CHILD_VALUE": "child"},
            failure_message=lambda code, tail: f"{code}: {' '.join(tail)}",
        )
    assert os.environ["STUDIO_TEST_CHILD_VALUE"] == "parent"


def test_driver_moves_large_binary_input_and_output_without_a_file_or_pipe_deadlock():
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    payload = bytes(range(256)) * 8192
    received = bytearray()
    messages = []
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('ready\\n'); sys.stdout.buffer.write(sys.stdin.buffer.read()[::-1])",
    ]

    SubprocessRunner().execute(
        command,
        input_bytes=payload,
        consume_output=received.extend,
        consume=messages.append,
        failure_message=lambda *_: "child failed",
        timeout_seconds=10,
    )

    assert received == payload[::-1]
    assert "ready" in "".join(messages)


def test_driver_closes_empty_input_and_accepts_an_early_closed_pipe():
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    for payload, program in [(b"", "import sys; assert sys.stdin.buffer.read() == b''"), (b"x" * 1000000, "pass")]:
        SubprocessRunner().execute(
            [sys.executable, "-c", program],
            input_bytes=payload,
            failure_message=lambda *_: "child failed",
        )


def test_driver_stops_its_group_when_the_output_consumer_fails():
    import pytest

    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    def reject(_chunk):
        raise ValueError("output limit")

    with pytest.raises(ValueError, match="output limit"):
        SubprocessRunner().execute(
            [
                sys.executable,
                "-c",
                "import sys,time; sys.stdout.buffer.write(b'clip'); sys.stdout.flush(); time.sleep(20)",
            ],
            consume_output=reject,
            terminate_group=True,
            failure_message=lambda *_: "child failed",
        )


def test_driver_group_timeout_stops_the_owned_child():
    import pytest

    from studio.l1_entities.errors import StudioError
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    with pytest.raises(StudioError, match="timed out"):
        SubprocessRunner().execute(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            timeout_seconds=0.01,
            terminate_group=True,
            failure_message=lambda *_: "child failed",
        )


def test_driver_cancellation_stops_the_owned_group():
    import pytest

    from studio.l1_entities.errors import Cancelled
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    with pytest.raises(Cancelled):
        SubprocessRunner().execute(
            [sys.executable, "-c", "import time; time.sleep(20)"],
            cancelled=lambda: True,
            terminate_group=True,
            failure_message=lambda *_: "child failed",
        )


def test_stop_group_ignores_an_already_removed_group(monkeypatch):
    from types import SimpleNamespace

    def gone(*_):
        raise ProcessLookupError

    monkeypatch.setattr("os.killpg", gone)

    _stop_process(cast(Any, SimpleNamespace(pid=123)), True)


def test_driver_keeps_cancellation_active_after_the_child_closes_its_streams():
    import time

    import pytest

    from studio.l1_entities.errors import Cancelled
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    started = time.monotonic()
    with pytest.raises(Cancelled):
        SubprocessRunner().execute(
            [sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(10)"],
            cancelled=lambda: time.monotonic() - started > 0.1,
            terminate_group=True,
            failure_message=lambda *_: "child failed",
        )
    assert time.monotonic() - started < 2


def test_driver_terminates_a_timed_out_child_after_its_streams_close():
    import time

    import pytest

    from studio.l1_entities.errors import StudioError
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    started = time.monotonic()
    with pytest.raises(StudioError, match="timed out"):
        SubprocessRunner().execute(
            [sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(10)"],
            timeout_seconds=0.1,
            terminate_group=True,
            failure_message=lambda *_: "child failed",
        )
    assert time.monotonic() - started < 2


def test_driver_reaps_its_child_when_the_cancellation_source_raises():
    import time

    import pytest

    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    def failed():
        raise RuntimeError("cancellation source failed")

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="source failed"):
        SubprocessRunner().execute(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            cancelled=failed,
            terminate_group=True,
            failure_message=lambda *_: "child failed",
        )
    assert time.monotonic() - started < 2


def test_driver_cancellation_kills_an_owned_grandchild_that_ignores_terminate(monkeypatch):
    import os
    import time

    import pytest

    from studio.l1_entities.errors import Cancelled
    from studio.l4_frameworks_and_drivers import subprocess_runner
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

    messages = []
    stopped = []
    original_stop = subprocess_runner._stop_process

    def stop(process, group):
        stopped.append(process.pid)
        original_stop(process, group)

    monkeypatch.setattr(subprocess_runner, "_stop_process", stop)
    grandchild = "import signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',file=sys.stderr,flush=True); time.sleep(10)"
    parent = (
        "import subprocess,sys,time; child=subprocess.Popen([sys.executable,'-c',sys.argv[1]]); "
        "print(child.pid,file=sys.stderr,flush=True); time.sleep(10)"
    )
    with pytest.raises(Cancelled):
        SubprocessRunner().execute(
            [sys.executable, "-c", parent, grandchild],
            consume=messages.append,
            cancelled=lambda: "ready" in "".join(messages),
            terminate_group=True,
            failure_message=lambda *_: "child failed",
            timeout_seconds=5,
        )
    pid = int(next(line for line in "".join(messages).splitlines() if line.isdigit()))
    for _ in range(100):
        state = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
        if not state or state.startswith("Z"):
            break
        time.sleep(0.01)
    else:
        os.kill(pid, 9)
        pytest.fail("the owned grandchild survived cancellation")
    assert len(stopped) == 1
