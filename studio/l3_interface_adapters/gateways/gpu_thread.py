"""Every model call runs on one thread.

MLX binds GPU streams to the thread that created them, and the HTTP server
answers each request on a fresh thread. Calling the model from a request thread
aborts the process with "There is no Stream(gpu, 1) in current thread". So
request threads hand their call to this one thread and wait for the answer.
"""

import queue
import threading


class GpuThread:
    def __init__(self):
        self._calls = queue.Queue()
        self._state_lock = threading.Lock()
        self._closed = False
        self._worker = threading.Thread(target=self._serve, daemon=True, name="gpu")
        self._worker.start()

    def call(self, function, *args):
        """Run `function(*args)` on the GPU thread. Blocks until it returns or raises."""
        done = threading.Event()
        outcome = {}
        with self._state_lock:
            if self._closed:
                raise RuntimeError("GPU worker is closed")
            self._calls.put((function, args, outcome, done))
        done.wait()
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("value")

    def close(self) -> None:
        """Finish accepted calls, stop the worker, and refuse later calls."""
        if threading.current_thread() is self._worker:
            raise RuntimeError("GPU worker cannot close itself")
        with self._state_lock:
            if not self._closed:
                self._closed = True
                self._calls.put(None)
        self._worker.join()

    def _serve(self):
        while True:
            call = self._calls.get()
            if call is None:
                return
            function, args, outcome, done = call
            try:
                outcome["value"] = function(*args)
            except BaseException as error:  # handed back to the caller, who raises it
                outcome["error"] = error
            finally:
                done.set()
