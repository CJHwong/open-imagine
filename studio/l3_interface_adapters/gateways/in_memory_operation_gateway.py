"""Bounded results and one reservation shared by every HTTP client."""

import copy
import json
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from studio.l1_entities.errors import BackendBusy, Cancelled, InvalidJob, OperationMissing
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult
from studio.l2_use_cases.boundaries.operation_gateway import OperationGateway
from studio.l3_interface_adapters.gateways.encrypted_result_gateway import EncryptedResultGateway, encryption_key


class InMemoryOperationGateway(OperationGateway):
    def __init__(
        self,
        max_count: int = 32,
        max_bytes: int = 256 * 1024 * 1024,
        max_age: float = 600,
        clock: Callable[[], float] = time.time,
        private_directory: Path | None = None,
    ):
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._results: dict[str, Any] = {}
        self._items: dict[str, list[Any]] = {}
        self._sizes: dict[str, int] = {}
        self._active: str | None = None
        self._reservation: str | None = None
        self._continuations: dict[str, tuple[int, float]] = {}
        self._clock = clock
        self._max_count = max_count
        self._max_bytes = max_bytes
        self._max_age = max_age
        self._private_results = EncryptedResultGateway(private_directory)
        self._private_keys: dict[str, bytes] = {}
        for record in self._private_results.records():
            operation_id = record["id"]
            if record["status"] in ("running", "stopping"):
                record.update(
                    status="failed", finished_at=self._clock(), error="The server restarted during this operation."
                )
                self._private_results.save_record(record)
            self._records[operation_id] = record
            self._items[operation_id] = [None] * record.get("batch_completed", 0)
            self._measure(operation_id)
        self._prune()

    def begin(self, description: dict[str, Any], private_key: str = "") -> dict[str, Any]:
        with self._lock:
            self._prune()
            if description.get("owner") and not private_key:
                raise InvalidJob("A private operation requires its original key.")
            if self._active is not None or self._reservation is not None:
                raise BackendBusy("The studio is busy. Read its state or cancel the active operation.")
            operation_id = uuid.uuid4().hex
            record = {
                **description,
                "id": operation_id,
                "status": "running",
                "started_at": self._clock(),
                "finished_at": None,
                "error": None,
                "result_retained": False,
            }
            size = len(json.dumps(record).encode())
            if description.get("owner"):
                key = encryption_key(private_key, operation_id)
                self._private_results.save_record(record)
                self._private_keys[operation_id] = key
            self._records[operation_id] = record
            self._sizes[operation_id] = size
            self._active = operation_id
            return self.get(operation_id)

    def busy(self) -> bool:
        with self._lock:
            self._prune()
            return self._active is not None or self._reservation is not None

    def exclusive(self, action: Callable[[], None]) -> None:
        with self._lock:
            if self.busy():
                raise BackendBusy("The studio is busy. Wait for the active operation.")
            self._reservation = "model-control"
        try:
            action()
        finally:
            with self._lock:
                self._reservation = None

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

    def active(self) -> dict[str, Any] | None:
        with self._lock:
            self._prune()
            return self.get(self._active) if self._active else None

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
            return record["finished_at"]

    def fail(self, operation_id: str, error: Exception) -> None:
        with self._lock:
            self._records[operation_id].update(
                status="cancelled" if isinstance(error, Cancelled) else "failed",
                finished_at=self._clock(),
                error=str(error),
            )
            self._active = None
            self._private_keys.pop(operation_id, None)
            self._measure(operation_id)
            self._prune()

    def expire(self) -> None:
        with self._lock:
            self._prune()

    def delete(self, operation_id: str) -> None:
        with self._lock:
            self.get(operation_id)
            if operation_id == self._active:
                raise BackendBusy("Cancel the operation before deleting it.")
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

    def _prune(self) -> None:
        if self._active in self._continuations and self._clock() >= self._continuations[self._active][1]:
            self._end_continuation(self._active)
        for operation_id in list(self._records):
            if operation_id == self._active:
                continue
            record = self._records[operation_id]
            private = bool(record.get("owner"))
            max_age = 3600 if private else self._max_age
            expired = self._clock() - record["finished_at"] > max_age
            public_ids = [identifier for identifier, entry in self._records.items() if not entry.get("owner")]
            over_limit = not private and (
                len(public_ids) > self._max_count
                or sum(self._sizes[identifier] for identifier in public_ids) > self._max_bytes
            )
            if expired or over_limit:
                self._discard(operation_id)


def result_bytes(result):
    if isinstance(result, VideoResult):
        return len(result.mp4 or b"")
    if isinstance(result, SpeechResult):
        return len(result.wav)
    return len(json.dumps(result).encode())
