"""Bounded results and one reservation shared by every HTTP client."""

import copy
import json
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from studio.l1_entities.errors import BackendBusy, Cancelled, InvalidJob, OperationMissing, QueueFull
from studio.l1_entities.music_job import MusicResult
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult
from studio.l2_use_cases.boundaries.operation_gateway import OperationGateway
from studio.l3_interface_adapters.gateways.encrypted_result_gateway import EncryptedResultGateway, encryption_key


class InMemoryOperationGateway(OperationGateway):
    # The longest a queued operation may sleep before it looks at the clock again. A
    # continuation lease has to end on time even when nothing else touches the queue.
    WAIT_SLICE_SECONDS = 1.0

    def __init__(
        self,
        max_count: int = 32,
        max_bytes: int = 256 * 1024 * 1024,
        max_age: float = 600,
        clock: Callable[[], float] = time.time,
        private_directory: Path | None = None,
        max_queue: int = 0,
        max_queue_bytes: int = 0,
        private_max_bytes: int = 0,
    ):
        if max_queue < 0:
            raise ValueError("max_queue must be zero or more")
        if max_queue_bytes < 0:
            raise ValueError("max_queue_bytes must be zero or more")
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._queue: list[str] = []
        self._max_queue = max_queue
        self._max_queue_bytes = max_queue_bytes
        self._records: dict[str, dict[str, Any]] = {}
        self._results: dict[str, Any] = {}
        self._items: dict[str, list[Any]] = {}
        self._sizes: dict[str, int] = {}
        self._active: str | None = None
        self._reservation: str | None = None
        self._closing = False
        self._continuations: dict[str, tuple[int, float]] = {}
        self._clock = clock
        self._max_count = max_count
        self._max_bytes = max_bytes
        self._max_age = max_age
        self._private_results = EncryptedResultGateway(private_directory, max_bytes=private_max_bytes)
        self._private_keys: dict[str, bytes] = {}
        for record in self._private_results.records():
            operation_id = record["id"]
            if record["status"] in ("queued", "running", "stopping"):
                record.update(
                    status="failed", finished_at=self._clock(), error="The server restarted during this operation."
                )
                self._private_results.save_record(record)
            self._records[operation_id] = record
            self._items[operation_id] = [None] * record.get("batch_completed", 0)
            self._measure(operation_id)
        self._prune()

    def begin(self, description: dict[str, Any], private_key: str = "", *, queued: bool = False) -> dict[str, Any]:
        with self._lock:
            self._prune()
            if self._closing:
                raise BackendBusy("The studio is stopping.")
            if description.get("owner") and not private_key:
                raise InvalidJob("A private operation requires its original key.")
            # A queue with no active operation is a handoff in progress: the head of the
            # queue is about to claim the slot. A new request must line up behind it, or
            # it takes the slot the queue was waiting for. `busy()` is the one definition
            # of taken, so model control and this admission cannot drift apart.
            waiting = self.busy()
            if waiting and (not queued or self._max_queue == 0):
                raise BackendBusy("The studio is busy. Read its state or cancel the active operation.")
            if waiting and len(self._queue) >= self._max_queue:
                raise QueueFull("The queue is full. Wait for a request to finish, or retry later.")
            # A waiting request holds its media. Counting the queue's bytes is what stops
            # a series of pushed clips from filling memory before the GPU does any work.
            held = sum(self._records[one].get("payload_bytes", 0) for one in self._queue)
            if waiting and self._max_queue_bytes and held + description.get("payload_bytes", 0) > self._max_queue_bytes:
                raise QueueFull("The queue is holding too much media. Wait for a request to finish, or retry later.")
            operation_id = uuid.uuid4().hex
            record = {
                **description,
                "id": operation_id,
                "status": "queued" if waiting else "running",
                "started_at": self._clock(),
                "finished_at": None,
                "error": None,
                "result_retained": False,
            }
            if waiting:
                record["pending_admission"] = True
            size = len(json.dumps(record).encode())
            if description.get("owner"):
                key = encryption_key(private_key, operation_id)
                self._private_results.save_record(record)
                self._private_keys[operation_id] = key
            self._records[operation_id] = record
            self._sizes[operation_id] = size
            if waiting:
                self._queue.append(operation_id)
            else:
                self._active = operation_id
            return self.get(operation_id)

    def queueing(self) -> bool:
        with self._lock:
            return self._max_queue > 0

    def wait_for_turn(self, operation_id: str) -> None:
        """Block until this queued operation is first and no other one is active.

        A reserved operation that was never queued is already the active one, so it
        returns at once. A cancel or a delete while it waits ends the wait.
        """
        with self._condition:
            while True:
                self._prune()
                record = self._records.get(operation_id)
                if record is None:
                    raise OperationMissing("The operation expired or does not exist.")
                if record["status"] in ("cancelled", "failed"):
                    raise Cancelled("The operation was cancelled before it started.")
                if operation_id not in self._queue:
                    return
                if self._active is None and self._reservation is None and self._queue[0] == operation_id:
                    self._queue.pop(0)
                    record.update(status="running", started_at=self._clock())
                    self._active = operation_id
                    return
                self._condition.wait(self._wait_slice())

    def _wait_slice(self) -> float:
        """How long a waiting thread may sleep: the next continuation lease, at most.

        `pause()` promises thirty seconds and nothing else wakes this queue when they
        run out. A waiter that slept indefinitely sat past the lease until an unrelated
        request happened to arrive, which is what the old HTTP-side timer did every
        sixty seconds.
        """
        if self._active not in self._continuations:
            return self.WAIT_SLICE_SECONDS
        remaining = self._continuations[self._active][1] - self._clock()
        return max(0.01, min(self.WAIT_SLICE_SECONDS, remaining))

    def queue_position(self, operation_id: str) -> int | None:
        with self._lock:
            if operation_id not in self._queue:
                return None
            return self._queue.index(operation_id) + 1

    def busy(self) -> bool:
        """Whether the one slot is taken, promised, about to be handed over, or shut.

        A queue with no active operation is a handoff in progress: the head is about to
        claim the slot. Model control goes through `exclusive()`, and one running in that
        window could switch the model or delete weights the head is about to load.
        """
        with self._lock:
            self._prune()
            return self._closing or self._active is not None or self._reservation is not None or bool(self._queue)

    def close_admission(self) -> None:
        """Refuse new work and end every queued request, so only the run in flight is left.

        Shutdown stops the operation that is running, but that run's `finish()` wakes the
        head of the queue, and the wake would take the slot while models and storage are
        being released. Marking the queued records cancelled ends their waits before that
        handoff can happen.
        """
        with self._lock:
            self._closing = True
            for operation_id in list(self._queue):
                self._records[operation_id].update(status="cancelled", finished_at=self._clock())
                self._private_keys.pop(operation_id, None)
                self._measure(operation_id)
            self._queue.clear()
            self._condition.notify_all()
            self._prune()

    def abandon(self, operation_id: str, error: Exception) -> None:
        """End an operation whose worker never started, queued or active.

        A request is reserved before its worker thread exists. When that thread cannot
        start, nothing else will ever finish the operation, and the one slot it holds
        stays taken for the life of the process.
        """
        with self._lock:
            if operation_id in self._queue:
                self._queue.remove(operation_id)
            self.fail(operation_id, error)

    def exclusive(self, action: Callable[[], None]) -> None:
        with self._lock:
            if self.busy():
                raise BackendBusy("The studio is busy. Wait for the operation holding the slot.")
            self._reservation = "model-control"
        try:
            action()
        finally:
            with self._lock:
                self._reservation = None
                self._condition.notify_all()

    def cancelling(self, operation_id: str) -> bool:
        with self._lock:
            return self._active == operation_id and self._records[operation_id]["status"] == "stopping"

    def escalate(self, operation_id: str, release: Callable[[], None]) -> None:
        with self._lock:
            if not self.cancelling(operation_id):
                return
            self._reservation = operation_id
        try:
            release()
        finally:
            with self._lock:
                self._reservation = None
                self._condition.notify_all()

    def active(self) -> dict[str, Any] | None:
        with self._lock:
            self._prune()
            return self.get(self._active) if self._active else None

    def pressure(self) -> dict[str, int]:
        """The queue's occupancy, for an operator reading the state.

        Read-only: no record changes and no waiter wakes. The bytes counted here are
        the media the waiting requests hold, which the queue's own budget also counts.
        """
        with self._lock:
            queued = [self._records[one] for one in self._queue]
            return {
                "queued": len(queued),
                "pending_admissions": sum(1 for one in queued if one.get("pending_admission")),
                "queued_bytes": sum(one.get("payload_bytes", 0) for one in queued),
                "max_queued": self._max_queue,
                "max_queued_bytes": self._max_queue_bytes,
            }

    def get(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            self._prune()
            if operation_id not in self._records:
                raise OperationMissing("The operation expired or does not exist.")
            return copy.deepcopy(self._records[operation_id])

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune()
            return copy.deepcopy(list(reversed(self._records.values())))

    def result(self, operation_id: str, private_key: str = "") -> Any:
        with self._lock:
            record = self.get(operation_id)
            result = self._results.get(operation_id)
            batch_manifest = (record.get("owner") and record.get("batch_total") and record["result_retained"]) or (
                isinstance(result, dict) and "items" in result
            )
            if record["status"] in ("running", "stopping") and not batch_manifest:
                raise BackendBusy("The operation has not finished.")
            if record.get("owner"):
                return self._private_results.read(operation_id, 0, encryption_key(private_key, operation_id))
            if operation_id not in self._results:
                raise OperationMissing("This operation has no retained result.")
            return self._results[operation_id]

    def stopping(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            self.get(operation_id)
            if operation_id in self._queue:
                self._queue.remove(operation_id)
                self._records[operation_id].update(status="cancelled", finished_at=self._clock())
                self._private_keys.pop(operation_id, None)
                self._measure(operation_id)
                self._condition.notify_all()
                return self.get(operation_id)
            if self._active != operation_id:
                raise BackendBusy("This operation is no longer active.")
            self._records[operation_id]["status"] = "stopping"
            if operation_id in self._continuations:
                self._end_continuation(operation_id)
            return self.get(operation_id)

    def retain(self, operation_id: str, result: object) -> None:
        with self._lock:
            if self._records[operation_id].get("owner"):
                self._private_results.write(operation_id, 0, result, self._private_keys[operation_id])
            else:
                self._results[operation_id] = result
            self._records[operation_id]["result_retained"] = True
            self._measure(operation_id)

    def _measure(self, operation_id: str) -> None:
        size = len(json.dumps(self._records[operation_id]).encode())
        if operation_id in self._results:
            size += result_bytes(self._results[operation_id])
        size += sum(result_bytes(item) for item in self._items.get(operation_id, []) if item is not None)
        if self._records[operation_id].get("owner"):
            size += self._private_results.size(operation_id)
            self._private_results.save_record(self._records[operation_id])
        self._sizes[operation_id] = size

    def append_image(self, operation_id: str, image: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            previous = self._results.get(operation_id, {"images": []})
            result = {"images": [*previous["images"], image]}
            self.retain(operation_id, result)
            return result

    def batch_started(self, operation_id, index, total):
        with self._lock:
            self._records[operation_id].update(batch_index=index, batch_total=total)

    def batch_completed(self, operation_id, result, metadata):
        with self._lock:
            private = bool(self._records[operation_id].get("owner"))
            self._items.setdefault(operation_id, []).append(None if private else result)
            completed = len(self._items[operation_id])
            self._records[operation_id]["batch_completed"] = completed
            previous = self._results.get(
                operation_id, {"items": [], "batch_total": self._records[operation_id]["batch_total"]}
            )
            if private:
                key = self._private_keys[operation_id]
                self._private_results.write(operation_id, completed, result, key)
                if self._records[operation_id]["result_retained"]:
                    previous = self._private_results.read(operation_id, 0, key)
            manifest = {**previous, "items": [*previous["items"], metadata], "completed": completed}
            self.retain(operation_id, manifest)
            return manifest

    def item_result(self, operation_id, index, private_key: str = ""):
        with self._lock:
            record = self.get(operation_id)
            items = self._items.get(operation_id, [])
            if not 1 <= index <= len(items):
                raise OperationMissing("This batch item has no retained result.")
            if record.get("owner"):
                return self._private_results.read(operation_id, index, encryption_key(private_key, operation_id))
            return items[index - 1]

    def pause(self, operation_id: str, next_index: int) -> None:
        with self._lock:
            self._continuations[operation_id] = (next_index, self._clock() + 30)
            if self._records[operation_id]["status"] == "stopping":
                self._end_continuation(operation_id)

    def resume(self, operation_id: str, index: int, client_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.get(operation_id)
            expected = self._continuations.get(operation_id)
            if (
                self._active != operation_id
                or expected is None
                or expected[0] != index
                or record["client_id"] != client_id
            ):
                raise BackendBusy("This batch continuation is no longer active.")
            del self._continuations[operation_id]
            return record

    def _end_continuation(self, operation_id: str) -> None:
        self._records[operation_id].update(status="cancelled", finished_at=self._clock())
        del self._continuations[operation_id]
        self._active = None
        self._condition.notify_all()

    def finish(self, operation_id: str, result: object) -> float:
        with self._lock:
            record = self._records[operation_id]
            cancelled = isinstance(result, dict) and result.get("cancelled") is True
            record.update(status="cancelled" if cancelled else "succeeded", finished_at=self._clock())
            if isinstance(result, VideoResult):
                record.update(
                    width=result.width,
                    height=result.height,
                    num_frames=result.num_frames,
                    frame_rate=result.frame_rate,
                    seed=result.seed,
                )
            if isinstance(result, MusicResult):
                record.update(
                    seconds=result.seconds, sample_rate=result.sample_rate, seed=result.seed, stub=result.stub
                )
            if isinstance(result, SpeechResult):
                record.update(
                    seconds=result.seconds,
                    sample_rate=result.sample_rate,
                    seed=result.seed,
                    steps=result.steps,
                )
                # A private record keeps no words of its caller, not even the spoken text.
                if not record.get("owner"):
                    record["prompt"] = result.text or record.get("prompt", "")
            self.retain(operation_id, result)
            self._active = None
            self._private_keys.pop(operation_id, None)
            self._measure(operation_id)
            self._prune()
            self._condition.notify_all()
            return record["finished_at"]

    def fail(self, operation_id: str, error: Exception) -> None:
        with self._lock:
            self._records[operation_id].update(
                status="cancelled" if isinstance(error, Cancelled) else "failed",
                finished_at=self._clock(),
                error=str(error),
            )
            # Only the operation that holds the slot may free it. A queued one that fails
            # before its turn leaves the active operation where it is.
            if self._active == operation_id:
                self._active = None
            self._private_keys.pop(operation_id, None)
            self._measure(operation_id)
            self._prune()
            self._condition.notify_all()

    def expire(self) -> None:
        with self._lock:
            self._prune()

    def delete(self, operation_id: str) -> None:
        with self._lock:
            self.get(operation_id)
            if operation_id == self._active:
                raise BackendBusy("Cancel the operation before deleting it.")
            if operation_id in self._queue:
                self._queue.remove(operation_id)
                self._condition.notify_all()
            self._discard(operation_id)

    def close(self) -> None:
        with self._lock:
            self._private_results.close()

    def _discard(self, operation_id: str) -> None:
        if self._records[operation_id].get("owner"):
            self._private_results.delete(operation_id)
        del self._records[operation_id]
        self._results.pop(operation_id, None)
        self._items.pop(operation_id, None)
        self._sizes.pop(operation_id, None)
        self._private_keys.pop(operation_id, None)

    def _prune(self) -> None:
        if self._active in self._continuations and self._clock() >= self._continuations[self._active][1]:
            self._end_continuation(self._active)
        public_ids = [identifier for identifier, record in self._records.items() if not record.get("owner")]
        public_count = len(public_ids)
        public_bytes = sum(self._sizes[identifier] for identifier in public_ids)
        # The newest finished public result survives the size and count limits. A caller
        # that just watched a large job succeed has to be able to fetch it: retention may
        # not contradict a success the studio already reported. Age still ends it. Only a
        # record that kept a result counts, because a queued request that is cancelled gets
        # a finish time without ever running, and it would otherwise protect itself while
        # evicting the run it was waiting behind. One operation runs at a time, so the
        # records that keep a result still finish in the order they were added.
        newest = None
        for identifier in public_ids:
            record = self._records[identifier]
            if record["finished_at"] is not None and record.get("result_retained"):
                newest = identifier
        for operation_id in list(self._records):
            if operation_id == self._active:
                continue
            record = self._records[operation_id]
            if record["finished_at"] is None:
                continue  # queued, so its caller still waits for it
            private = bool(record.get("owner"))
            max_age = 3600 if private else self._max_age
            expired = self._clock() - record["finished_at"] > max_age
            over_limit = not private and (public_count > self._max_count or public_bytes > self._max_bytes)
            if expired or (over_limit and operation_id != newest):
                if not private:
                    public_count -= 1
                    public_bytes -= self._sizes[operation_id]
                self._discard(operation_id)


def result_bytes(result):
    if isinstance(result, VideoResult):
        return len(result.mp4 or b"")
    if isinstance(result, MusicResult):
        return len(result.wav) + len(json.dumps(result.metadata).encode()) + len(result.score.encode())
    if isinstance(result, SpeechResult):
        return len(result.wav)
    return len(json.dumps(result).encode())
