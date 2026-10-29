"""Authenticated private results and redacted operation records in a local database."""

import base64
import fcntl
import json
import os
import sqlite3
import weakref
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from studio.l1_entities.errors import OperationMissing, StudioError
from studio.l1_entities.lora import LoraUse
from studio.l1_entities.music_job import MusicResult
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult


def encryption_key(private_key: str, operation_id: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=operation_id.encode(), info=b"studio.private-results.v1"
    ).derive(private_key.encode("ascii"))


class EncryptedResultGateway:
    def __init__(self, directory: Path | None = None):
        filename = ":memory:"
        storage_lock = None
        if directory is not None:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            storage_lock = os.open(directory / "storage.lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(storage_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(storage_lock)
                raise StudioError(
                    "Private result storage is already in use. Choose another --private-results-dir."
                ) from None
            filename = str(directory / "private-results.sqlite3")
        try:
            if directory is not None:
                descriptor = os.open(filename, os.O_CREAT | os.O_RDWR, 0o600)
                try:
                    os.fchmod(descriptor, 0o600)
                finally:
                    os.close(descriptor)
            self._connection = sqlite3.connect(filename, check_same_thread=False)
        except Exception:
            if storage_lock is not None:
                os.close(storage_lock)
            raise
        self._finalizer = weakref.finalize(self, close_storage, self._connection, storage_lock)
        with self._connection:
            self._connection.execute("PRAGMA secure_delete=ON")
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, record TEXT NOT NULL)"
            )
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS results "
                "(operation_id TEXT, item_index INTEGER, ciphertext BLOB NOT NULL, PRIMARY KEY (operation_id, item_index))"
            )

    def records(self) -> list[dict[str, Any]]:
        return [json.loads(row[0]) for row in self._connection.execute("SELECT record FROM operations ORDER BY rowid")]

    def save_record(self, record: dict[str, Any]) -> None:
        record = dict(record)
        if record.get("error"):
            record["error"] = "The private operation failed."
        with self._connection:
            self._connection.execute(
                "INSERT INTO operations VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET record=excluded.record",
                (record["id"], json.dumps(record)),
            )

    def write(self, operation_id: str, index: int, result: Any, key: bytes) -> None:
        nonce = os.urandom(12)
        ciphertext = nonce + AESGCM(key).encrypt(nonce, encode_result(result), f"{operation_id}/{index}".encode())
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO results VALUES (?, ?, ?)", (operation_id, index, ciphertext)
            )

    def read(self, operation_id: str, index: int, key: bytes) -> Any:
        row = self._connection.execute(
            "SELECT ciphertext FROM results WHERE operation_id=? AND item_index=?", (operation_id, index)
        ).fetchone()
        if row is None:
            raise OperationMissing("This operation has no retained result.")
        ciphertext = row[0]
        try:
            plaintext = AESGCM(key).decrypt(ciphertext[:12], ciphertext[12:], f"{operation_id}/{index}".encode())
        except (InvalidTag, ValueError):
            raise OperationMissing("This operation has no readable result.") from None
        return decode_result(plaintext)

    def size(self, operation_id: str) -> int:
        return self._connection.execute(
            "SELECT COALESCE(SUM(length(ciphertext)), 0) FROM results WHERE operation_id=?", (operation_id,)
        ).fetchone()[0]

    def delete(self, operation_id: str) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM results WHERE operation_id=?", (operation_id,))
            self._connection.execute("DELETE FROM operations WHERE id=?", (operation_id,))

    def close(self) -> None:
        self._finalizer()


def close_storage(connection: sqlite3.Connection, storage_lock: int | None) -> None:
    connection.close()
    if storage_lock is not None:
        os.close(storage_lock)


def encode_result(result: Any) -> bytes:
    if isinstance(result, VideoResult):
        fields = asdict(result)
        fields["mp4"] = base64.b64encode(result.mp4).decode() if result.mp4 is not None else None
        envelope = {"type": "video", "value": fields}
    elif isinstance(result, (MusicResult, SpeechResult)):
        fields = asdict(result)
        fields["wav"] = base64.b64encode(result.wav).decode()
        envelope = {"type": "music" if isinstance(result, MusicResult) else "voice", "value": fields}
    else:
        envelope = {"type": "json", "value": result}
    return json.dumps(envelope).encode()


def decode_result(plaintext: bytes) -> Any:
    envelope = json.loads(plaintext)
    fields = envelope["value"]
    if envelope["type"] == "video":
        fields["mp4"] = base64.b64decode(fields["mp4"]) if fields["mp4"] is not None else None
        fields["loras"] = tuple(LoraUse(**entry) for entry in fields["loras"])
        return VideoResult(**fields)
    if envelope["type"] == "music":
        fields["wav"] = base64.b64decode(fields["wav"])
        return MusicResult(**fields)
    if envelope["type"] == "voice":
        fields["wav"] = base64.b64decode(fields["wav"])
        return SpeechResult(**fields)
    return fields
