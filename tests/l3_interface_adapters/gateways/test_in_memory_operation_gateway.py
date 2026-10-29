import pytest

from studio.l1_entities.errors import BackendBusy, Cancelled
from studio.l3_interface_adapters.gateways.in_memory_operation_gateway import InMemoryOperationGateway as Operations


def active_id(operations):
    operation = operations.active()
    assert operation is not None
    return operation["id"]


def test_one_operation_owns_the_slot_and_retains_its_result():
    operations = Operations()
    first = operations.begin({"kind": "image", "prompt": "pear"})
    with pytest.raises(BackendBusy):
        operations.begin({"kind": "video"})
    operations.finish(first["id"], {"images": []})
    assert operations.active() is None
    assert operations.get(first["id"])["status"] == "succeeded"
    assert operations.result(first["id"]) == {"images": []}


def test_failures_and_cancellation_release_the_slot():
    operations = Operations()
    first = operations.begin({"kind": "video"})
    operations.fail(first["id"], Cancelled("stopped"))
    assert operations.get(first["id"])["status"] == "cancelled"
    second = operations.begin({"kind": "image"})
    operations.fail(second["id"], ValueError("bad"))
    assert operations.get(second["id"])["error"] == "bad"


@pytest.mark.parametrize("status", ["running", "stopping"])
def test_active_batches_expose_the_retained_manifest(status):
    operations = Operations()
    operation = operations.begin({"kind": "voice"})
    operation_id = operation["id"]
    manifest = {"items": [], "batch_total": 2, "completed": 0}
    operations.retain(operation_id, manifest)
    operations.batch_started(operation_id, 1, 2)
    if status == "stopping":
        operations.stopping(operation_id)
    assert operations.result(operation_id) == manifest
    updated = operations.batch_completed(operation_id, {"audio": "wav"}, {"index": 1})
    assert operations.result(operation_id) == updated
    assert updated["completed"] == 1


@pytest.mark.parametrize("result", [None, {"images": []}, "wav"])
@pytest.mark.parametrize("status", ["running", "stopping"])
def test_active_single_results_still_require_completion(result, status):
    operations = Operations()
    operation = operations.begin({"kind": "voice"})
    if result is not None:
        operations.retain(operation["id"], result)
    if status == "stopping":
        operations.stopping(operation["id"])
    with pytest.raises(BackendBusy, match="has not finished"):
        operations.result(operation["id"])


def test_stopping_only_targets_the_active_operation():
    from studio.l1_entities.errors import OperationMissing

    operations = Operations()
    with pytest.raises(OperationMissing):
        operations.get("unknown")
    first = operations.begin({"kind": "image"})
    assert active_id(operations) == first["id"]
    assert operations.stopping(first["id"])["status"] == "stopping"
    with pytest.raises(BackendBusy):
        operations.result(first["id"])
    operations.finish(first["id"], {"cancelled": True})
    assert operations.get(first["id"])["status"] == "cancelled"
    with pytest.raises(BackendBusy):
        operations.stopping(first["id"])
    second = operations.begin({"kind": "image"})
    operations.fail(second["id"], ValueError("bad"))
    with pytest.raises(OperationMissing):
        operations.result(second["id"])
    assert [one["id"] for one in operations.recent()] == [second["id"], first["id"]]


def test_count_time_and_bytes_bound_retention_without_evicting_active_work():
    from studio.l1_entities.errors import OperationMissing
    from studio.l1_entities.video_job import VideoResult

    now = [0]
    operations = Operations(max_count=1, clock=lambda: now[0], max_age=10, max_bytes=1024)
    first = operations.begin({"kind": "image"})
    operations.finish(first["id"], {})
    second = operations.begin({"kind": "image"})
    assert active_id(operations) == second["id"]
    with pytest.raises(OperationMissing):
        operations.get(first["id"])
    now[0] = 20
    assert active_id(operations) == second["id"]
    operations.finish(second["id"], {})
    assert operations.get(second["id"])["status"] == "succeeded"
    now[0] = 31
    with pytest.raises(OperationMissing):
        operations.get(second["id"])
    third = operations.begin({"kind": "video"})
    operations.finish(third["id"], VideoResult(b"x" * 2048, 8, 8, 9, 24, 7))
    assert operations.recent() == []
    fourth = operations.begin({"kind": "video"})
    operations.finish(fourth["id"], VideoResult(None, 8, 8, 9, 24, None, stub=True))
    assert operations.result(fourth["id"]).stub


def test_voice_retention_counts_the_effective_instruction_in_its_byte_limit():
    from studio.l1_entities.voice_job import SpeechResult

    operations = Operations(max_bytes=1024)
    operation = operations.begin({"kind": "voice"})
    operations.finish(operation["id"], SpeechResult(b"wav", 1, 16000, 7, 4, text="word " * 1000))
    assert operations.recent() == []


def test_continuation_expires_only_between_engine_calls():
    now = [0]
    operations = Operations(clock=lambda: now[0])
    first = operations.begin({"kind": "image", "client_id": "tab"})
    operations.append_image(first["id"], {"png_base64": "png"})
    operations.pause(first["id"], 2)
    with pytest.raises(BackendBusy):
        operations.resume(first["id"], 2, "other")
    now[0] = 29
    operations.resume(first["id"], 2, "tab")
    now[0] = 100
    assert active_id(operations) == first["id"]
    operations.pause(first["id"], 3)
    now[0] = 131
    assert operations.active() is None
    assert operations.get(first["id"])["status"] == "cancelled"
    assert len(operations.result(first["id"])["images"]) == 1
    with pytest.raises(BackendBusy):
        operations.resume(first["id"], 3, "tab")


def test_cancel_after_engine_return_does_not_leave_a_continuation_wait():
    operations = Operations()
    operation = operations.begin({"kind": "image", "client_id": ""})
    operations.stopping(operation["id"])
    operations.pause(operation["id"], 2)
    assert operations.active() is None
    assert operations.get(operation["id"])["status"] == "cancelled"


def test_escalation_blocks_new_owners_until_the_release_finishes():
    import threading

    operations = Operations()
    operation = operations.begin({"kind": "image"})
    assert operations.busy() and not operations.cancelling(operation["id"])
    operations.stopping(operation["id"])
    assert operations.cancelling(operation["id"])
    observed = threading.Event()

    def release():
        operations.finish(operation["id"], {})
        assert operations.active() is None and operations.busy()
        with pytest.raises(BackendBusy):
            operations.begin({"kind": "video"})
        worker = threading.Thread(target=lambda: (operations.recent(), observed.set()))
        worker.start()
        worker.join(2)
        assert observed.is_set(), "release must not hold the operation lock"

    operations.escalate(operation["id"], release)
    assert not operations.busy()
    next_operation = operations.begin({"kind": "video"})
    operations.escalate(operation["id"], lambda: pytest.fail("old cancel released a newer owner"))
    assert active_id(operations) == next_operation["id"]


def test_failed_escalation_releases_its_reservation():
    operations = Operations()
    operation = operations.begin({"kind": "image"})
    operations.stopping(operation["id"])

    def release():
        operations.finish(operation["id"], {})
        raise RuntimeError("release failed")

    with pytest.raises(RuntimeError, match="release failed"):
        operations.escalate(operation["id"], release)
    assert not operations.busy()


def test_model_controls_reserve_the_slot_and_release_it_after_errors():
    operations = Operations()

    def control():
        assert operations.busy()
        with pytest.raises(BackendBusy):
            operations.begin({"kind": "image"})
        with pytest.raises(BackendBusy):
            operations.exclusive(lambda: None)
        raise ValueError("control failed")

    with pytest.raises(ValueError, match="control failed"):
        operations.exclusive(control)
    assert not operations.busy()


def test_private_results_survive_restart_and_repeated_reads(tmp_path):
    key = "private key"
    operations = Operations(private_directory=tmp_path)
    operation = operations.begin({"kind": "image", "owner": "digest"}, private_key=key)
    result = {"images": [{"png_base64": "private pixels", "prompt": "private words"}]}
    operations.finish(operation["id"], result)
    assert operation["id"] not in operations._results
    assert operation["id"] not in operations._private_keys
    operations.close()

    restored = Operations(private_directory=tmp_path)
    assert restored.result(operation["id"], key) == result
    assert restored.result(operation["id"], key) == result
    assert restored.get(operation["id"])["result_retained"] is True
    restored.close()


def test_private_batch_items_survive_restart_and_repeated_reads(tmp_path):
    operations = Operations(private_directory=tmp_path)
    operation = operations.begin({"kind": "image", "owner": "digest", "batch_total": 2}, private_key="key")
    operations.retain(operation["id"], {"items": [], "batch_total": 2, "completed": 0})
    operations.batch_completed(operation["id"], {"images": ["one"]}, {"index": 1})
    manifest = operations.batch_completed(operation["id"], {"images": ["two"]}, {"index": 2})
    operations.finish(operation["id"], manifest)
    operations.close()
    restored = Operations(private_directory=tmp_path)
    assert restored.result(operation["id"], "key") == manifest
    assert restored.item_result(operation["id"], 2, "key") == {"images": ["two"]}
    assert restored.item_result(operation["id"], 2, "key") == {"images": ["two"]}
    restored.close()


def test_private_expiry_is_one_hour_and_public_expiry_is_ten_minutes(tmp_path):
    from studio.l1_entities.errors import OperationMissing

    now = [0.0]
    operations = Operations(private_directory=tmp_path, clock=lambda: now[0], max_count=1, max_bytes=4096)
    private = operations.begin({"kind": "image", "owner": "digest"}, private_key="key")
    operations.finish(private["id"], {"images": ["secret"]})
    public = operations.begin({"kind": "image"})
    operations.finish(public["id"], {"images": []})
    now[0] = 601
    operations.expire()
    assert public["id"] not in operations._records
    assert operations.result(private["id"], "key") == {"images": ["secret"]}
    now[0] = 3601
    operations.expire()
    assert operations._private_results.records() == []
    with pytest.raises(OperationMissing):
        operations.result(private["id"], "key")
    operations.close()


def test_restart_marks_interrupted_private_operations_failed(tmp_path):
    operations = Operations(private_directory=tmp_path)
    operation = operations.begin({"kind": "image", "owner": "digest"}, private_key="key")
    with pytest.raises(BackendBusy, match="before deleting"):
        operations.delete(operation["id"])
    operations.close()
    restored = Operations(private_directory=tmp_path)
    assert restored.get(operation["id"])["status"] == "failed"
    assert not restored.busy()
    restored.delete(operation["id"])
    assert restored._private_results.records() == []
    restored.close()


@pytest.mark.parametrize("owner,prompt", [("", "Hello there"), ("digest", "")])
def test_a_private_speech_record_keeps_no_spoken_text(owner, prompt):
    from studio.l1_entities.voice_job import SpeechResult

    operations = Operations()
    operation = operations.begin({"kind": "voice", "prompt": "", "owner": owner}, private_key="key" if owner else "")
    operations.finish(operation["id"], SpeechResult(b"wav", 1.0, 24000, 7, 4, text="Hello there"))

    assert operations.get(operation["id"])["prompt"] == prompt


def test_default_retention_expires_ten_minutes_after_completion():
    from studio.l1_entities.errors import OperationMissing

    now = [0.0]
    operations = Operations(clock=lambda: now[0])
    operation = operations.begin({"kind": "image"})
    now[0] = 900.0
    assert operations.get(operation["id"])["status"] == "running"
    operations.finish(operation["id"], {"images": []})
    now[0] = 1499.0
    assert operations.result(operation["id"]) == {"images": []}
    now[0] = 1501.0
    with pytest.raises(OperationMissing):
        operations.result(operation["id"])


def test_a_private_operation_requires_the_original_key():
    from studio.l1_entities.errors import InvalidJob

    operations = Operations()
    with pytest.raises(InvalidJob, match="original key"):
        operations.begin({"kind": "image", "owner": "digest"})
    assert not operations.busy()


def test_a_failed_disk_reservation_leaves_the_studio_free(monkeypatch):
    operations = Operations()

    def fail_write(record):
        raise OSError("disk full")

    monkeypatch.setattr(operations._private_results, "save_record", fail_write)
    with pytest.raises(OSError, match="disk full"):
        operations.begin({"kind": "image", "owner": "digest"}, private_key="key")
    assert not operations.busy()
    assert operations._records == {} and operations._private_keys == {}


def test_private_item_zero_cannot_read_the_main_result():
    from studio.l1_entities.errors import OperationMissing

    operations = Operations()
    operation = operations.begin({"kind": "image", "owner": "digest"}, private_key="key")
    operations.finish(operation["id"], {"images": ["private"]})
    with pytest.raises(OperationMissing):
        operations.item_result(operation["id"], 0, "key")


def test_a_private_batch_can_publish_its_first_item_without_a_manifest():
    operations = Operations()
    operation = operations.begin({"kind": "image", "owner": "digest", "batch_total": 1}, private_key="key")
    manifest = operations.batch_completed(operation["id"], {"images": ["one"]}, {"index": 1})
    assert manifest["completed"] == 1
    assert operations.result(operation["id"], "key") == manifest
    assert operations.item_result(operation["id"], 1, "key") == {"images": ["one"]}
