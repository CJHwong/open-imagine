"""A long-lived engine process that answers one JSON job per line.

An engine goes into a child when it cannot live in the server process: another
dependency tree, as every engine here pins its own, or another language. The
child speaks JSON over pipes, not files and not flags. Clips as paths would put
them on disk and the text as an argument would put it in `ps`, and the server
promises neither.

The child stays up between jobs, because building a pipeline costs tens of
seconds and nothing about it depends on the job.

start_new_session puts the child in its own process group, and cancel kills
that whole group. Killing the child alone does not work: a script with a
`uv run` shebang runs as uv, with the interpreter as its child. Killing uv left
the interpreter denoising to the last step, which made cancel look like it did
nothing for 20 seconds.

A job that goes unanswered means the child died. Its stderr is the only account
of why, so the lines that are not steps are kept, and the last few go into the
error. An edit child that never started used to report nothing but "the engine
stopped answering", with `env: uv: No such file or directory` thrown away.

A child that must put a clip on disk puts it in the folder named by
SCRATCH_ENV. This side makes that folder per child and removes it when the
child goes. Cancel kills a child with SIGKILL, so the child's own cleanup never
runs, and a clip it wrote to its own temp folder stayed on disk.

A child marks an error that the job caused with "kind": "input". The client
then gets a refused request, not a server failure.

A child that ends on its own takes its exit code into the error, as EngineExited.
A child can refuse in a way its gateway must tell apart, and its words cannot carry
that: torch printed warnings after an H3 child's refusal, and the message kept only
those. The code is read before the group is killed, because the kill replaces it.

A child prints `ready` on stderr once its engine is loaded. Starting a child
takes no time, but loading takes a minute, and a server that reported itself
ready before that made its first request pay for the load.
"""

import contextlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable

from studio.l1_entities.errors import Cancelled, InvalidJob

STEP_LINE = re.compile(rb"step (\d+)/(\d+)")
SAID_LINES = 20  # how much of the child's stderr to hold for a failure message
SAID_IN_MESSAGE = 3
READY_LINE = b"ready"
SCRATCH_ENV = "SPEECH_GEN_SCRATCH"
EXIT_GRACE = 5  # seconds a child whose pipes closed gets to end, so its own exit code is read


class EngineExited(RuntimeError):
    """The engine ended without an answer. `exit_code` is the code it ended with, or None
    when it was still there after EXIT_GRACE."""

    def __init__(self, message: str, exit_code: int | None):
        super().__init__(message)
        self.exit_code = exit_code


def _answers(line: bytes, request_id: str) -> bool:
    """Whether this line is the answer to the request that carried `request_id`."""
    try:
        reply = json.loads(line)
    except ValueError:
        return False
    return isinstance(reply, dict) and reply.get("request_id") == request_id


class StdioChild:
    def __init__(self, command: list[str], *, startup_timeout: float = 1800, request_timeout: float = 3600):
        if any(not math.isfinite(timeout) or timeout <= 0 for timeout in (startup_timeout, request_timeout)):
            raise ValueError("engine deadlines must be positive finite seconds")
        self._command = command
        self._startup_timeout = startup_timeout
        self._request_timeout = request_timeout
        self._proc = None
        self._pgid = None
        self._on_step = None
        self._last_step = 0
        self._step_error = None
        self._said = deque(maxlen=SAID_LINES)
        self._steps = None
        self._ready = threading.Event()
        self._loaded = False
        self._scratch = None
        # Bumped for each child this instance starts. A watcher can outlive its job by
        # up to a second, and the generation is what keeps it off the next engine.
        self._generation = 0
        # Generation and process ownership move together, so a stale watcher can never
        # check the generation and then capture the child that replaced it.
        self._lifecycle = threading.RLock()

    def running(self) -> bool:
        """Whether the engine is still there, its group included.

        The child starts a session, so its process group is the engine. A wrapper
        can outlive the process we started while still holding the pipes, and
        reading the process alone would call that engine dead: cancel never
        fires, a read blocks with nothing to interrupt it, and ensure() starts a
        second model on the GPU beside the first.
        """
        proc, pgid = self._proc, self._pgid
        if proc is None or pgid is None:
            return False
        proc.poll()  # reap the leader: its zombie alone would hold the group open
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True  # it is there, we just may not signal it
        return True

    def ensure(self) -> None:
        with self._lifecycle:
            if self.running():
                return
            self._remove_scratch()  # a child that died alone left its folder
            self._generation += 1
            self._scratch = tempfile.mkdtemp(prefix="speech-gen-")
            try:
                self._proc = subprocess.Popen(
                    self._command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    env={**os.environ, SCRATCH_ENV: self._scratch},
                )
            except BaseException:
                # A spawn that failed leaves a folder nothing owns.
                self._remove_scratch()
                raise
            # Taken while the leader is alive: start_new_session makes it the group
            # leader, so the id is its pid. Looking it up at kill time fails when the
            # leader died first, and then a wrapper that outlived it is never killed.
            # Set before the watcher starts, so no other thread reads a stale id.
            self._pgid = self._proc.pid
            self._ready = threading.Event()
            self._loaded = False
            self._steps = threading.Thread(
                target=self._watch_steps, args=(self._proc, self._ready, self._generation), daemon=True
            )
            self._steps.start()

    def wait_ready(self) -> None:
        """Start the child if it is not running, and block until its engine is loaded.

        A child that ends before it says `ready` ends the wait, and its last words
        go into the error.
        """
        self.ensure()
        if not self._ready.wait(self._startup_timeout):
            self.stop()
            self._drain()
            raise RuntimeError("the engine loading timed out" + self._last_words())
        if not self._loaded:
            exit_code = self._exit_code()
            self.stop()
            raise EngineExited("the engine stopped while loading" + self._last_words(), exit_code)

    def stop(self) -> None:
        """Kill the child and free its memory."""
        if self._proc is None:
            return
        self._kill()
        self._proc = None

    def request(
        self,
        payload: dict,
        on_step: Callable[[int, int], None],
        should_stop: Callable[[], bool],
    ) -> dict:
        """Send one job and wait for its answer.

        Raises Cancelled when should_stop() turned true and the child was killed,
        and RuntimeError when the child reports an error or dies.
        """
        self._said.clear()  # a job's reason is what the child says about that job
        self._step_error = None
        self.ensure()
        generation = self._generation
        self._on_step = on_step
        self._last_step = 0
        killed = threading.Event()
        answered = threading.Event()
        timed_out = threading.Event()
        watcher_errors = []
        watcher = threading.Thread(
            target=self._watch_cancel,
            args=(should_stop, killed, answered, timed_out, watcher_errors, generation),
            daemon=True,
        )
        watcher.start()
        try:
            answer = self._exchange(payload)
        except BaseException:
            self.stop()
            self._drain()
            raise
        finally:
            answered.set()
            watcher.join(timeout=1)
        if watcher_errors:
            self.stop()
            self._drain()
            raise watcher_errors[0]
        if self._step_error is not None:
            # The callback that reports progress raised. That is the request's failure,
            # not a dead engine: the kill it caused must not hide the original error. A
            # callback that raises after the child has answered cannot fail that answer,
            # because the two pipes are read by different threads and the answer is whole
            # by the time it is read.
            error, self._step_error = self._step_error, None
            self.stop()
            self._drain()
            raise error
        if timed_out.is_set():
            self.stop()
            self._drain()
            raise RuntimeError("the engine request timed out" + self._last_words())
        # Only a kill counts as a cancel. A cancel that lands after the answer
        # keeps the finished clip and the warm child.
        if killed.is_set():
            self._proc = None  # the kill took the engine with it
            self._drain()  # so no reader is left to append to the next job's message
            raise Cancelled(f"stopped at step {self._last_step}")
        if not answer:
            exit_code = self._exit_code()
            self.stop()
            self._drain()
            raise EngineExited("the engine stopped answering" + self._last_words(), exit_code)
        # `_read_reply` returns only a line that parsed as a JSON object answering this
        # request, so this parse cannot fail. A line that is not an answer is kept for the
        # failure message instead, and the reply behind it is still the one read.
        reply = json.loads(answer)
        if "error" in reply:
            if reply.get("kind") == "input":
                raise InvalidJob(reply["error"])
            raise RuntimeError(reply["error"])
        return reply

    def _exit_code(self) -> int | None:
        """The code the child ended with. Its pipes close a moment before a `uv run` wrapper
        exits, so it gets EXIT_GRACE to end before the kill that would replace the code."""
        proc = self._proc
        if proc is None:
            return None
        try:
            return proc.wait(timeout=EXIT_GRACE)
        except subprocess.TimeoutExpired:
            return None

    def _exchange(self, payload: dict) -> bytes:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            return b""  # the same answer as a dead child
        request_id = uuid.uuid4().hex
        try:
            proc.stdin.write(json.dumps({**payload, "request_id": request_id}).encode() + b"\n")
            proc.stdin.flush()
            return self._read_reply(proc.stdout, request_id)
        except (BrokenPipeError, OSError):
            return b""

    def _read_reply(self, stdout, request_id: str) -> bytes:
        """The line that answers this request, or b"" when the child is gone.

        A child echoes the id it was sent, and only that line is an answer. An engine
        library may print on stdout: mlx-audio prints its load notes there, and a log
        line that happened to be JSON was taken as the reply, which failed the job and
        put every later reply one job out of step. Anything else is kept for a failure
        message instead.
        """
        while True:
            line = stdout.readline()
            if not line:
                return line
            if _answers(line, request_id):
                return line
            self._said.append(line.decode("utf-8", "replace").strip())

    def _watch_steps(self, proc, ready: threading.Event, generation: int | None = None) -> None:
        """Turn the child's step lines into progress, for the child's whole life.

        Everything else it prints is kept for the moment a job goes unanswered,
        because that is where the child says what went wrong.
        """
        for line in proc.stderr:
            if generation is not None and generation != self._generation:
                return  # this child was replaced; its lines are not this job's
            if line.strip() == READY_LINE:
                self._loaded = True
                ready.set()
                continue
            match = STEP_LINE.search(line)
            if match:
                if self._on_step is not None:
                    self._last_step = int(match.group(1))
                    try:
                        self._on_step(self._last_step, int(match.group(2)))
                    except BaseException as error:
                        # A callback that raises must not take down the only reader of the
                        # child's stderr. A chatty engine then fills that pipe and blocks,
                        # and the job waits out its deadline with no reason to show. Keep
                        # reading, stop the child, and let the request raise this error.
                        if self._step_error is None:
                            self._step_error = error
                        self._kill(generation)
                continue
            self._said.append(line.decode("utf-8", "replace").strip())
        ready.set()  # the child has gone: a wait for it to load ends here

    def _drain(self) -> None:
        """Read out what the child left in the pipe, after the kill closed it.

        The kill comes first because a wrapper can outlive the process we started
        and hold the pipe open: only the group kill reaches it. When that kill
        lands, nothing written before it is lost, since a killed group cannot
        write again and the kernel keeps the buffer readable. When it does not
        land, this bound is what stops the read from waiting forever.
        """
        if self._steps is not None:
            self._steps.join(timeout=1.0)

    def _last_words(self) -> str:
        """What the child said before it went quiet, for the failure message."""
        said = [line for line in self._said if line]
        if not said:
            return ""
        return ". It last said: " + " | ".join(said[-SAID_IN_MESSAGE:])

    def _watch_cancel(self, should_stop, killed, answered, timed_out, errors, generation: int | None = None) -> None:
        """Cancel means kill. There is no polite way to interrupt the engine.

        The watch ends with the job. The child outlives it, and a watcher left
        polling an idle child used to kill it on the next cancel of anything.
        """
        deadline = time.monotonic() + self._request_timeout
        while not answered.is_set() and self.running():
            try:
                cancel_requested = should_stop()
            except BaseException as error:
                if answered.is_set():
                    return
                errors.append(error)
                self._kill(generation)
                return
            if answered.is_set():
                return
            if cancel_requested:
                killed.set()
                self._kill(generation)
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out.set()
                self._kill(generation)
                return
            answered.wait(min(0.4, remaining))

    def _kill(self, generation: int | None = None) -> None:
        """Kill the child and anything it started, by the group id taken at spawn.

        A watcher can outlive the job that started it by up to a second. A kill that
        names an older generation is a no-op, so it can neither signal the engine that
        replaced its child nor remove that engine's scratch folder.
        """
        with self._lifecycle:
            if generation is not None and generation != self._generation:
                return
            proc, pgid, scratch = self._proc, self._pgid, self._scratch
        if proc is None or pgid is None:
            return
        try:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()  # the group is already gone
            # A process that will not be reaped must not turn a cancel into an exception
            # of its own, and its scratch folder has to go whether or not it is reaped.
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)
        finally:
            self._remove_scratch(scratch)

    def _remove_scratch(self, scratch: str | None = None) -> None:
        """Remove one child's folder, and any clip in it. The child is gone, or about to start.

        The folder is named by the caller when it belongs to a child that may already
        have been replaced, so removing it cannot touch the engine in use.
        """
        folder = self._scratch if scratch is None else scratch
        if folder is None:
            return
        with contextlib.suppress(FileNotFoundError):  # already gone meets the goal
            shutil.rmtree(folder)
        if self._scratch == folder:
            self._scratch = None
