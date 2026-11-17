import io
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from tests.support import REPO_ROOT

FAKE_CHILD = REPO_ROOT / "tests/support/voice_fake_child.py"

FAKE = FAKE_CHILD


@pytest.fixture
def child():
    # Through a shell, like the real children run through `uv run`: the engine is
    # a grandchild, and cancel must reach it.
    runner = StdioChild(["/bin/sh", "-c", f'"{sys.executable}" "{FAKE}"; exit $?'])
    yield runner
    runner.stop()


def never():
    return False


def test_a_silent_load_has_a_deadline_and_reaps_its_child():
    runner = StdioChild([sys.executable, "-c", "import time; time.sleep(60)"], startup_timeout=0.1)
    started = time.monotonic()
    try:
        runner.ensure()
        assert runner._proc is not None
        pid = runner._proc.pid
        with pytest.raises(RuntimeError, match="loading timed out"):
            runner.wait_ready()
        assert time.monotonic() - started < 3
        assert not runner.running()
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        runner.stop()


def test_a_silent_reply_has_a_deadline_and_releases_the_process_group():
    command = "import sys, time; print('ready', file=sys.stderr, flush=True); sys.stdin.readline(); time.sleep(60)"
    runner = StdioChild([sys.executable, "-c", command], request_timeout=0.1)
    try:
        runner.wait_ready()
        assert runner._proc is not None
        pid = runner._proc.pid
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="request timed out"):
            runner.request({}, lambda *_: None, never)
        assert time.monotonic() - started < 3
        assert not runner.running()
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        runner.stop()


def test_an_exchange_failure_stops_its_cancel_watcher(child, monkeypatch):
    ended = threading.Event()
    watch = child._watch_cancel

    def track(*arguments):
        try:
            watch(*arguments)
        finally:
            ended.set()

    monkeypatch.setattr(child, "_watch_cancel", track)
    with monkeypatch.context() as patch:
        patch.setattr(child, "_exchange", Mock(side_effect=TypeError("invalid payload")))
        with pytest.raises(TypeError, match="invalid payload"):
            child.request({}, lambda *_: None, never)
        assert ended.wait(1), "the failed request left its watcher running"
    assert child.request({"echo": "next"}, lambda *_: None, never)["echo"] == "next"


@pytest.mark.parametrize("name", ["startup_timeout", "request_timeout"])
@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan")])
def test_engine_deadlines_require_positive_finite_seconds(name, seconds):
    with pytest.raises(ValueError, match="positive finite"):
        StdioChild([], **{name: seconds})


def test_a_failed_cancel_callback_cannot_disable_the_request_deadline():
    runner = StdioChild([sys.executable, "-c", "import time; time.sleep(60)"], request_timeout=0.1)
    try:
        with pytest.raises(ValueError, match="cancel probe failed"):
            runner.request({}, lambda *_: None, Mock(side_effect=ValueError("cancel probe failed")))
        assert not runner.running()
    finally:
        runner.stop()


@pytest.mark.parametrize("callback_error", [False, True])
def test_a_late_cancel_callback_cannot_kill_the_next_request(monkeypatch, callback_error):
    runner = StdioChild([])
    monkeypatch.setattr(runner, "running", lambda: True)
    killed = Mock()
    monkeypatch.setattr(runner, "_kill", killed)
    answered = threading.Event()

    def late_cancel():
        answered.set()
        if callback_error:
            raise ValueError("stale probe")
        return True

    errors = []
    runner._watch_cancel(late_cancel, threading.Event(), answered, threading.Event(), errors)
    killed.assert_not_called()
    assert errors == []


def test_a_job_comes_back_with_its_steps(child):
    steps = []
    reply = child.request({"echo": "hi", "steps": 3}, lambda step, total: steps.append((step, total)), never)
    assert reply["echo"] == "hi"
    time.sleep(0.1)
    assert steps == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_the_child_stays_up_between_jobs(child):
    first = child.request({"echo": 1}, lambda *_: None, never)
    second = child.request({"echo": 2}, lambda *_: None, never)
    assert first["pid"] == second["pid"]


def test_an_engine_error_is_raised(child):
    with pytest.raises(RuntimeError, match="out of memory"):
        child.request({"error": "out of memory"}, lambda *_: None, never)
    assert child.running()


def test_a_crash_is_raised_and_the_next_job_restarts_it(child):
    with pytest.raises(RuntimeError, match="stopped answering"):
        child.request({"crash": True}, lambda *_: None, never)
    assert child.request({"echo": "back"}, lambda *_: None, never)["echo"] == "back"


def test_cancel_kills_the_whole_group(child):
    pid = child.request({"echo": 0}, lambda *_: None, never)["pid"]
    started = time.time()
    with pytest.raises(Cancelled, match="stopped at step"):
        child.request({"steps": 50, "pause": 0.1}, lambda *_: None, lambda: time.time() - started > 0.5)
    assert time.time() - started < 2
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert not child.running()


def test_a_dead_child_says_what_it_reported_during_the_job(child):
    """The child's stderr is the only account of its death, so the message carries it."""
    with pytest.raises(RuntimeError, match="say no such file"):
        child.request({"say": "no such file", "crash": True}, lambda *_: None, never)


def test_a_failure_does_not_wait_for_a_reason_that_cannot_come():
    """A wrapper can outlive the process it started and hold the pipe open.

    The kill closes that pipe, so the wait for the child's last words ends at
    once. Reading before killing burns the whole timeout instead, every time,
    because the survivor is still holding the other end.
    """
    command = f'( sleep 2; echo "late reason" >&2 ) 1>/dev/null & exec "{sys.executable}" "{FAKE}"'
    runner = StdioChild(["/bin/sh", "-c", command])
    try:
        began = time.time()
        with pytest.raises(RuntimeError, match="stopped answering"):
            runner.request({"crash": True}, lambda *_: None, never)
        assert time.time() - began < 0.9, "the failure waited out the drain timeout"
    finally:
        runner.stop()


def test_the_engine_is_alive_while_its_group_is():
    """A wrapper can outlive the process we started and still hold its pipes."""
    command = f'( sleep 2 ) 1>/dev/null & exec "{sys.executable}" "{FAKE}"'
    runner = StdioChild(["/bin/sh", "-c", command])
    try:
        runner.request({"echo": "one", "exit": True}, lambda *_: None, never)
        time.sleep(0.3)  # let the process we started die, so only the group is left
        assert runner.running(), "the engine left the pipes to its group"
    finally:
        runner.stop()


def test_cancel_reaches_an_engine_whose_wrapper_holds_the_pipes():
    """A survivor on stdout blocks the read, so the cancel has to kill the group.

    sh gives a background job /dev/null for stdin, so without `<&0` nothing held stdin once
    the engine exited. The next write then broke the pipe, and the job failed before the
    cancel, whenever the engine finished exiting first: a loaded machine lost that race.
    """
    command = f'( sleep 5 ) <&0 & exec "{sys.executable}" "{FAKE}"'
    runner = StdioChild(["/bin/sh", "-c", command])
    try:
        runner.request({"echo": "one", "exit": True}, lambda *_: None, never)
        began = time.time()
        with pytest.raises(Cancelled, match="stopped at step"):
            runner.request({"steps": 50, "pause": 0.1}, lambda *_: None, lambda: time.time() - began > 0.5)
        assert time.time() - began < 3
    finally:
        runner.stop()


def test_a_dead_child_does_not_report_the_previous_jobs_log(child):
    """What it said about an earlier job is not the reason this one died."""
    child.request({"say": "all good"}, lambda *_: None, never)
    with pytest.raises(RuntimeError) as raised:
        child.request({"crash": True}, lambda *_: None, never)
    assert "all good" not in str(raised.value)


def test_a_group_that_is_gone_is_not_a_live_engine():
    """The group is probed after the leader is reaped, so an empty group reads as dead.

    Reading the process alone is not enough: a wrapper can outlive it holding the
    pipes, and ensure() would start a second model on the GPU beside the first.
    """
    runner = StdioChild([sys.executable, str(FAKE)])
    try:
        pid = runner.request({"echo": "one"}, lambda *_: None, never)["pid"]
        os.killpg(pid, signal.SIGKILL)  # start_new_session makes the group id the leader's pid
        time.sleep(0.2)
        assert not runner.running()
    finally:
        runner.stop()


def test_a_group_that_cannot_be_signalled_is_still_alive(monkeypatch):
    """EPERM means the engine is there and we may not signal it.

    Reading that as dead would make cancel fire with nothing to kill, and
    ensure() would start a second model beside the running one.
    """
    runner = StdioChild([sys.executable, str(FAKE)])
    try:
        runner.request({"echo": "one"}, lambda *_: None, never)
        with monkeypatch.context() as patch:
            patch.setattr(os, "killpg", Mock(side_effect=PermissionError("not mine to signal")))
            assert runner.running()
    finally:
        runner.stop()


def test_a_write_to_a_killed_engine_comes_back_empty():
    """A killed group closes the pipe, so the next exchange answers nothing.

    That answer is what turns into "the engine stopped answering" instead of a
    read that waits for a child that will never write again.
    """
    runner = StdioChild([sys.executable, str(FAKE)])
    try:
        pid = runner.request({"echo": "one"}, lambda *_: None, never)["pid"]
        os.killpg(pid, signal.SIGKILL)
        time.sleep(0.2)
        assert runner._exchange({"echo": "two"}) == b""
    finally:
        runner.stop()


def test_a_child_with_no_pipes_answers_nothing():
    """Before ensure() there is no process to write to, and that is the same as a dead child."""
    runner = StdioChild([sys.executable, str(FAKE)])
    assert runner._exchange({"echo": "one"}) == b""


def test_killing_a_child_that_never_started_has_nothing_to_kill():
    """The group id is taken at spawn. A stop before ensure() has none to kill."""
    runner = StdioChild([sys.executable, str(FAKE)])
    runner._kill()
    assert not runner.running()


def test_a_step_line_read_before_a_handler_is_installed_is_dropped():
    """ensure() starts the stderr reader, and request() installs the handler after it.

    A step line that lands in that gap has nobody to tell, so the reader skips it
    rather than calling None. The prose is kept, because a failure message needs it.
    """
    runner = StdioChild([sys.executable, str(FAKE)])
    runner._watch_steps(Mock(stderr=[b"step 1/4\n", b"env: uv: No such file or directory\n"]), threading.Event())
    assert runner._last_step == 0
    assert list(runner._said) == ["env: uv: No such file or directory"]


def test_draining_a_child_that_never_started_waits_for_no_thread():
    """The join is on the stderr reader, which only exists once ensure() has run.

    request() reaches _drain() only after ensure(), so this guards a child that was
    built and never started: there is no thread, and none of the one-second wait.
    """
    runner = StdioChild([sys.executable, str(FAKE)])
    began = time.time()
    runner._drain()
    assert time.time() - began < 0.5
    assert runner._steps is None


def test_wait_ready_returns_once_the_engine_says_it_is_loaded(child):
    child.wait_ready()
    assert child.running()
    child.wait_ready()  # a loaded child is not waited on again


def test_a_child_that_dies_while_loading_says_why():
    runner = StdioChild(["/bin/sh", "-c", "echo 'weights not found' >&2; exit 1"])
    with pytest.raises(RuntimeError, match=r"stopped while loading\. It last said: weights not found"):
        runner.wait_ready()
    assert not runner.running()


def test_a_line_that_is_not_json_on_stdout_is_not_taken_as_the_reply(child):
    reply = child.request({"noise": "Loading weights...", "echo": 1}, lambda s, t: None, lambda: False)
    assert reply["echo"] == 1
    assert child.request({"echo": 2}, lambda s, t: None, lambda: False)["echo"] == 2  # still in step


def test_a_child_that_dies_after_printing_on_stdout_says_what_it_printed(child):
    with pytest.raises(RuntimeError, match=r"It last said: .*Loading weights"):
        child.request({"noise": "Loading weights...", "crash": True}, lambda s, t: None, lambda: False)


def test_a_line_that_only_looks_like_a_reply_is_not_taken_as_one(child):
    """A child answers the id it was sent. A library's log line that happens to be JSON,
    or half a reply, is kept for a failure message, and the job stays in step."""
    reply = child.request({"noise": "{half a reply", "echo": 1}, lambda s, t: None, lambda: False)

    assert reply["echo"] == 1
    assert list(child._said)[-1] == "{half a reply"
    assert child.request({"echo": 2}, lambda s, t: None, lambda: False)["echo"] == 2


def test_a_json_line_carrying_another_request_id_is_not_the_reply(child):
    reply = child.request(
        {"noise": '{"request_id": "someone-else", "echo": "wrong"}', "echo": 3}, lambda s, t: None, lambda: False
    )

    assert reply["echo"] == 3
    assert child.request({"echo": 4}, lambda s, t: None, lambda: False)["echo"] == 4


def test_an_error_the_job_caused_is_a_refused_request(child):
    with pytest.raises(InvalidJob, match="no speech in this text"):
        child.request({"error": "no speech in this text", "kind": "input"}, lambda s, t: None, lambda: False)


def scratch_of(runner) -> Path:
    return Path(runner._scratch)


def test_the_scratch_folder_goes_when_the_child_stops(child):
    child.request({"write_scratch": True}, lambda s, t: None, lambda: False)
    folder = scratch_of(child)
    assert (folder / "ref.wav").exists()
    child.stop()
    assert not folder.exists()


def test_the_scratch_folder_goes_when_a_cancel_kills_the_child(child):
    """SIGKILL skips the child's own cleanup, so the clip it wrote must go from here."""
    child.request({"write_scratch": True}, lambda s, t: None, lambda: False)
    folder = scratch_of(child)
    with pytest.raises(Cancelled):
        child.request({"steps": 50, "pause": 0.1}, lambda s, t: None, lambda: True)
    assert not folder.exists()


def test_a_child_that_died_alone_has_its_folder_removed_at_the_next_start(child):
    child.request({"write_scratch": True}, lambda s, t: None, lambda: False)
    folder = scratch_of(child)
    with pytest.raises(RuntimeError):
        child.request({"crash": True}, lambda s, t: None, lambda: False)
    child.ensure()
    assert not folder.exists() and scratch_of(child) != folder


def test_a_progress_callback_that_raises_fails_the_request_with_its_own_error():
    """The callback is the caller's code, and it must not take down the only reader of the
    child's stderr. A chatty engine then fills that pipe and blocks, and the job waits out
    its deadline with no reason to show."""
    # The child sends no answer. A step line and an answer travel on two pipes, so the
    # answer can be read first, and this test would then pass or fail by scheduling.
    command = (
        "import sys, time\n"
        "print('ready', file=sys.stderr, flush=True)\n"
        "sys.stdin.readline()\n"
        "print('step 1/3', file=sys.stderr, flush=True)\n"
        "time.sleep(60)\n"
    )
    runner = StdioChild([sys.executable, "-c", command])

    def explode(*_):
        raise ValueError("progress exploded")

    try:
        runner.wait_ready()
        started = time.monotonic()
        with pytest.raises(ValueError, match="progress exploded"):
            runner.request({}, explode, never)
        assert time.monotonic() - started < 5
        assert not runner.running()
    finally:
        runner.stop()


def test_a_child_that_will_not_be_reaped_still_loses_its_scratch_folder(tmp_path):
    """A wait that raises is a process that did not go. The folder still has to go, and
    the cancel still has to look like a cancel."""
    runner = StdioChild([sys.executable, "-c", "import time; time.sleep(60)"])
    folder = tmp_path / "scratch"
    folder.mkdir()
    runner._proc = Mock()
    runner._proc.wait.side_effect = subprocess.TimeoutExpired("child", 5)
    runner._pgid = 2**22  # no such group: the fallback kill is the path taken
    runner._scratch = str(folder)

    runner._kill()

    assert not folder.exists()


def test_the_stderr_reader_keeps_draining_and_keeps_the_first_callback_error():
    """A second raising callback must not replace the first error, which is the cause, and
    the reader has to reach the end of the pipe either way."""

    class CountingChild(StdioChild):
        kills = 0

        def _kill(self, generation: int | None = None) -> None:
            self.kills += 1

    runner = CountingChild([sys.executable, "-c", "pass"])
    reported = []

    def explode(step, total):
        reported.append(step)
        raise ValueError(f"progress {step}")

    runner._on_step = explode

    runner._watch_steps(SimpleNamespace(stderr=[b"step 1/2\n", b"step 2/2\n"]), threading.Event())

    assert reported == [1, 2]  # the reader kept reading after the first raise
    assert str(runner._step_error) == "progress 1"
    assert runner.kills == 2


def test_a_late_kill_does_not_signal_the_engine_that_replaced_its_child(monkeypatch):
    """A cancel watcher can outlive its job by a second. By then the instance may have
    started another child, and the old watcher must not kill that one."""
    runner = StdioChild(["engine"])
    first = Mock()
    first.wait.return_value = 0
    runner._proc, runner._pgid, runner._generation = first, 4242, 1
    signalled = []
    monkeypatch.setattr(os, "killpg", lambda pgid, _number: signalled.append(pgid))

    runner._generation = 2  # a new child is now the one this instance runs
    runner._kill(1)

    assert signalled == []
    assert first.kill.call_count == 0


def test_a_late_cleanup_removes_only_its_own_child_folder(tmp_path):
    """The folder is captured with the process, so a late kill cannot delete the folder
    the engine in use reads its clips from."""
    runner = StdioChild(["engine"])
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    runner._scratch = str(new)

    runner._remove_scratch(str(old))

    assert not old.exists()
    assert new.is_dir()
    assert runner._scratch == str(new)


def test_the_reader_of_a_replaced_child_reports_nothing_to_the_next_job():
    """A step reader outlives its child by a moment. Its lines belong to the job that
    started it, and must not reach the handler the next job installed."""
    runner = StdioChild(["engine"])
    runner._generation = 2
    seen = []
    runner._on_step = lambda step, total: seen.append(step)

    runner._watch_steps(SimpleNamespace(stderr=io.BytesIO(b"step 7/9\n")), threading.Event(), 1)

    assert seen == []


def test_a_spawn_that_fails_removes_its_scratch_folder(monkeypatch, tmp_path):
    """A Popen that raises leaves a folder nothing owns, and repeated attempts pile up."""
    runner = StdioChild(["engine"])
    created = []

    def make(*_args, **_options):
        folder = tmp_path / f"scratch-{len(created)}"
        folder.mkdir()
        created.append(folder)
        return folder

    monkeypatch.setattr("tempfile.mkdtemp", make)
    monkeypatch.setattr(subprocess, "Popen", Mock(side_effect=FileNotFoundError("no engine")))

    with pytest.raises(FileNotFoundError, match="no engine"):
        runner.ensure()

    assert created and not created[0].exists()
    assert runner._scratch is None
