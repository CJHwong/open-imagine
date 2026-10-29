import hashlib

import pytest

from studio.l1_entities.errors import OperationMissing
from studio.l1_entities.lora import LoraUse
from studio.l1_entities.music_job import MusicResult
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult
from studio.l3_interface_adapters.gateways.encrypted_result_gateway import EncryptedResultGateway, encryption_key

KEY = "a private random caller key of at least 32 characters"


@pytest.mark.parametrize(
    "result",
    [
        {"images": [{"png_base64": "secret picture", "prompt": "secret prompt"}]},
        VideoResult(b"secret movie", 64, 64, 9, 24, 7, loras=(LoraUse("style", 0.5),)),
        VideoResult(None, 64, 64, 9, 24, None, stub=True),
        MusicResult(b"secret song", 2.5, 48000, 7, "secret score", {"lyrics": "secret lyrics"}),
        MusicResult(b"", 0, 48000, 8, "secret score", {"mode": "plan"}, stub=True),
        SpeechResult(b"secret audio", 1.0, 24000, 7, 4, text="secret words"),
    ],
)
def test_results_remain_encrypted_and_survive_reopening(tmp_path, result):
    vault = EncryptedResultGateway(tmp_path)
    secret = encryption_key(KEY, "operation")
    vault.save_record({"id": "operation", "owner": "digest", "finished_at": 0})
    vault.write("operation", 0, result, secret)
    vault.close()

    restored = EncryptedResultGateway(tmp_path)
    assert restored.read("operation", 0, secret) == result
    assert restored.read("operation", 0, secret) == result
    assert restored.records()[0]["id"] == "operation"
    assert restored.size("operation") > 0
    assert all(b"secret" not in path.read_bytes() for path in tmp_path.iterdir())
    assert (tmp_path / "private-results.sqlite3").stat().st_mode & 0o777 == 0o600
    restored.close()


def test_wrong_keys_and_changed_ciphertext_do_not_return_plaintext(tmp_path):
    vault = EncryptedResultGateway(tmp_path)
    secret = encryption_key(KEY, "operation")
    vault.save_record({"id": "operation"})
    vault.write("operation", 0, {"prompt": "secret"}, secret)
    with pytest.raises(OperationMissing):
        vault.read("operation", 0, encryption_key("wrong key", "operation"))
    with vault._connection:
        vault._connection.execute("UPDATE results SET ciphertext = ?", (b"changed",))
    with pytest.raises(OperationMissing):
        vault.read("operation", 0, secret)
    vault.close()


def test_delete_removes_the_record_and_every_batch_item(tmp_path):
    vault = EncryptedResultGateway(tmp_path)
    vault.save_record({"id": "operation"})
    vault.write("operation", 1, {"images": []}, encryption_key(KEY, "operation"))
    vault.delete("operation")
    assert vault.records() == []
    assert vault.size("operation") == 0
    with pytest.raises(OperationMissing):
        vault.read("operation", 1, encryption_key(KEY, "operation"))
    vault.close()


def test_stored_authentication_hash_cannot_decrypt_results():
    digest = hashlib.sha256(KEY.encode()).hexdigest()
    assert encryption_key(KEY, "operation") != encryption_key(digest, "operation")


def test_a_second_server_cannot_open_the_same_private_storage(tmp_path):
    from studio.l1_entities.errors import StudioError

    first = EncryptedResultGateway(tmp_path)
    with pytest.raises(StudioError, match="already in use"):
        EncryptedResultGateway(tmp_path)
    first.close()
    second = EncryptedResultGateway(tmp_path)
    second.close()


def test_a_database_path_failure_releases_storage_ownership(tmp_path):
    path = tmp_path / "private-results.sqlite3"
    path.mkdir()
    with pytest.raises(IsADirectoryError):
        EncryptedResultGateway(tmp_path)
    path.rmdir()
    recovered = EncryptedResultGateway(tmp_path)
    recovered.close()


@pytest.mark.parametrize("persistent", [False, True])
def test_a_connection_failure_releases_storage_ownership(tmp_path, monkeypatch, persistent):
    import sqlite3

    directory = tmp_path if persistent else None

    def fail_connect(*args, **kwargs):
        raise sqlite3.OperationalError("cannot open database")

    with monkeypatch.context() as scoped:
        scoped.setattr(sqlite3, "connect", fail_connect)
        with pytest.raises(sqlite3.OperationalError, match="cannot open"):
            EncryptedResultGateway(directory)
    recovered = EncryptedResultGateway(directory)
    recovered.close()
