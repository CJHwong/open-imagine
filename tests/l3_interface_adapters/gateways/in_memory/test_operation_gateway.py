import threading
import time

import pytest

from studio.l1_entities.errors import BackendBusy, Cancelled, OperationMissing, QueueFull
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult
from studio.l3_interface_adapters.gateways.in_memory.operation_gateway import InMemoryOperationGateway as Operations


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
    # The count is over its limit, and the one finished record is the newest. A caller that
    # has not fetched it yet still gets it.
    assert operations.get(first["id"])["status"] == "succeeded"
    now[0] = 20
    assert active_id(operations) == second["id"]
    operations.finish(second["id"], {})
    assert operations.get(second["id"])["status"] == "succeeded"
    # The newest moved, so the older result gives way to the count limit now.
    with pytest.raises(OperationMissing):
        operations.get(first["id"])
    now[0] = 31
    with pytest.raises(OperationMissing):
        operations.get(second["id"])
    third = operations.begin({"kind": "video"})
    operations.finish(third["id"], VideoResult(b"x" * 2048, 8, 8, 9, 24, 7))
    # Over the byte limit, and still here: it is the newest finished result, which its
    # caller has not fetched yet.
    assert [one["id"] for one in operations.recent()] == [third["id"]]
    fourth = operations.begin({"kind": "video"})
    operations.finish(fourth["id"], VideoResult(None, 8, 8, 9, 24, None, stub=True))
    assert operations.result(fourth["id"]).stub
    with pytest.raises(OperationMissing):
        operations.result(third["id"])


def test_voice_retention_counts_the_effective_instruction_in_its_byte_limit():
    from studio.l1_entities.voice_job import SpeechResult

    operations = Operations(max_bytes=1024)
    operation = operations.begin({"kind": "voice"})
    operations.finish(operation["id"], SpeechResult(b"wav", 1, 16000, 7, 4, text="word " * 1000))

    # The words the backend spoke are part of what this record holds. It is over the byte
    # limit, and it stays because it is the newest one.
    assert operations._sizes[operation["id"]] > 1024
    assert operations.result(operation["id"]).wav == b"wav"


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


@pytest.mark.parametrize("kind", ["video", "voice", "music"])
def test_private_output_facts_remain_encrypted_after_completion_and_restart(tmp_path, kind):
    from studio.l1_entities.errors import OperationMissing
    from studio.l1_entities.music_job import MusicResult
    from studio.l1_entities.video_job import VideoResult
    from studio.l1_entities.voice_job import SpeechResult

    result = {
        "video": VideoResult(b"private clip", 512, 288, 73, 24, 8675309),
        "voice": SpeechResult(b"private voice", 2.5, 24000, 8675309, 4, text="private words"),
        "music": MusicResult(b"private music", 2.5, 48000, 8675309, "private score", {}),
    }[kind]
    operations = Operations(private_directory=tmp_path)
    operation = operations.begin({"kind": kind, "owner": "digest", "width": 512, "seed": 8675309}, "key")
    operations.finish(operation["id"], result)
    assert operations.get(operation["id"])["seed"] == 8675309
    stored = operations._private_results.records()[0]
    assert (
        not {"width", "height", "num_frames", "frame_rate", "seed", "seconds", "sample_rate", "steps", "stub"}
        & stored.keys()
    )
    operations.close()
    assert b"8675309" not in (tmp_path / "private-results.sqlite3").read_bytes()
    restored = Operations(private_directory=tmp_path)
    assert restored.result(operation["id"], "key") == result
    assert restored.result(operation["id"], "key") == result
    with pytest.raises(OperationMissing):
        restored.result(operation["id"], "wrong key")
    restored.delete(operation["id"])
    assert restored.recent() == []
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


def test_a_queue_accepts_requests_behind_the_active_one_and_reports_positions():
    operations = Operations(max_queue=2)
    first = operations.begin({"kind": "image"})

    second = operations.begin({"kind": "image"}, queued=True)
    third = operations.begin({"kind": "image"}, queued=True)

    assert first["status"] == "running"
    assert second["status"] == "queued" and operations.queue_position(second["id"]) == 1
    assert third["status"] == "queued" and operations.queue_position(third["id"]) == 2
    assert operations.queueing() and operations.busy()
    with pytest.raises(QueueFull, match="queue is full"):
        operations.begin({"kind": "image"}, queued=True)


def test_a_queue_disabled_studio_refuses_a_second_request():
    operations = Operations()
    operations.begin({"kind": "image"})

    assert not operations.queueing()
    with pytest.raises(BackendBusy):
        operations.begin({"kind": "image"}, queued=True)


def test_wait_for_turn_claims_the_first_queued_operation_when_the_active_one_ends():
    operations = Operations(max_queue=1)
    first = operations.begin({"kind": "image"})
    second = operations.begin({"kind": "image"}, queued=True)
    claimed = threading.Event()

    def wait():
        operations.wait_for_turn(second["id"])
        claimed.set()

    thread = threading.Thread(target=wait)
    thread.start()
    assert not claimed.wait(0.2)
    assert active_id(operations) == first["id"]

    operations.finish(first["id"], {})
    assert claimed.wait(2)
    thread.join(2)
    assert operations.get(second["id"])["status"] == "running"
    assert active_id(operations) == second["id"]
    assert operations.queue_position(second["id"]) is None


def test_a_new_request_queues_behind_the_operation_that_is_next_in_line():
    """The slot is free while the head of the queue wakes up. A request that arrives in
    that window must line up behind it, not take its place."""
    operations = Operations(max_queue=2)
    first = operations.begin({"kind": "image"})
    second = operations.begin({"kind": "image"}, queued=True)
    operations.finish(first["id"], {})

    third = operations.begin({"kind": "image"}, queued=True)

    assert operations.active() is None
    assert operations.get(third["id"])["status"] == "queued"
    assert operations.queue_position(second["id"]) == 1
    assert operations.queue_position(third["id"]) == 2

    operations.wait_for_turn(second["id"])

    assert active_id(operations) == second["id"]


def test_queued_work_runs_one_operation_at_a_time_and_leaves_none_behind():
    operations = Operations(max_queue=8)
    first = operations.begin({"kind": "image"})
    guard = threading.Lock()
    state = {"running": 0, "peak": 0}
    finished = []

    def work(index):
        operation = operations.begin({"kind": "image", "index": index}, queued=True)
        operations.wait_for_turn(operation["id"])
        with guard:
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        time.sleep(0.005)
        with guard:
            state["running"] -= 1
            finished.append(index)
        operations.finish(operation["id"], {"index": index})

    threads = [threading.Thread(target=work, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    operations.finish(first["id"], {})
    for thread in threads:
        thread.join(5)

    assert not any(thread.is_alive() for thread in threads)
    assert len(finished) == 8
    assert state["peak"] == 1
    assert operations.active() is None
    assert operations.busy() is False


def test_a_direct_reservation_does_not_wait_for_a_turn():
    operations = Operations()
    operation = operations.begin({"kind": "image"})

    operations.wait_for_turn(operation["id"])

    assert operations.get(operation["id"])["status"] == "running"


def test_cancelling_a_queued_operation_wakes_its_waiter():
    operations = Operations(max_queue=1)
    first = operations.begin({"kind": "image"})
    second = operations.begin({"kind": "image"}, queued=True)
    outcome = []

    def wait():
        try:
            operations.wait_for_turn(second["id"])
        except Cancelled as error:
            outcome.append(str(error))

    thread = threading.Thread(target=wait)
    thread.start()
    assert operations.stopping(second["id"])["status"] == "cancelled"
    thread.join(2)

    assert outcome == ["The operation was cancelled before it started."]
    assert operations.busy() and active_id(operations) == first["id"]
    with pytest.raises(BackendBusy):
        operations.stopping(second["id"])


def test_deleting_a_queued_operation_wakes_its_waiter_with_missing():
    operations = Operations(max_queue=1)
    operations.begin({"kind": "image"})
    queued = operations.begin({"kind": "image"}, queued=True)
    outcome = []

    def wait():
        try:
            operations.wait_for_turn(queued["id"])
        except OperationMissing:
            outcome.append("missing")

    thread = threading.Thread(target=wait)
    thread.start()
    operations.delete(queued["id"])
    thread.join(2)

    assert outcome == ["missing"]
    assert operations.queue_position(queued["id"]) is None


def test_a_queued_operation_is_not_pruned_while_its_caller_waits():
    operations = Operations(max_count=1, max_age=0, max_queue=1, clock=lambda: 100.0)
    operations.begin({"kind": "image"})
    queued = operations.begin({"kind": "image"}, queued=True)

    operations.expire()

    assert operations.get(queued["id"])["status"] == "queued"


def test_restart_marks_a_queued_private_operation_failed(tmp_path):
    operations = Operations(private_directory=tmp_path, max_queue=1)
    operations.begin({"kind": "image", "owner": "digest"}, private_key="key")
    queued = operations.begin({"kind": "image", "owner": "digest"}, private_key="key", queued=True)
    operations.close()

    restored = Operations(private_directory=tmp_path)

    assert restored.get(queued["id"])["status"] == "failed"
    restored.close()


def test_private_queued_cancel_persists_without_releasing_the_active_operation(tmp_path):
    operations = Operations(private_directory=tmp_path, max_queue=1)
    running = operations.begin({"kind": "image"})
    queued = operations.begin({"kind": "image", "owner": "digest"}, private_key="test-key", queued=True)

    operations.stopping(queued["id"])

    assert active_id(operations) == running["id"]
    assert queued["id"] not in operations._private_keys
    operations.close()
    restored = Operations(private_directory=tmp_path)
    assert restored.get(queued["id"])["status"] == "cancelled"
    restored.close()


def test_delete_drops_a_queued_private_key():
    operations = Operations(max_queue=1)
    operations.begin({"kind": "image"})
    queued = operations.begin({"kind": "image", "owner": "digest"}, private_key="test-key", queued=True)

    operations.delete(queued["id"])

    assert queued["id"] not in operations._private_keys


def test_prune_reads_each_public_size_once():
    class CountingSizes(dict):
        reads = 0

        def __getitem__(self, key):
            self.reads += 1
            return super().__getitem__(key)

    operations = Operations(max_count=1000, max_bytes=1024**3)
    for _ in range(100):
        operation = operations.begin({"kind": "image"})
        operations.finish(operation["id"], {})
    operations._sizes = CountingSizes(operations._sizes)

    operations.expire()

    assert operations._sizes.reads == 100


def test_a_negative_queue_size_is_refused():
    with pytest.raises(ValueError, match="max_queue"):
        Operations(max_queue=-1)


def test_a_queued_operation_notices_a_lease_that_ran_out_on_its_own():
    """`pause()` promises thirty seconds. Nothing else touches the queue when they end, so
    the operation next in line has to look at the clock by itself. It waited forever until
    the server's sixty-second timer happened to fire."""
    now = [0.0]
    operations = Operations(clock=lambda: now[0], max_queue=2)
    first = operations.begin({"kind": "video"})
    second = operations.begin({"kind": "video"}, queued=True)
    operations.pause(first["id"], 1)
    woken = threading.Event()

    threading.Thread(target=lambda: (operations.wait_for_turn(second["id"]), woken.set()), daemon=True).start()
    time.sleep(0.1)
    now[0] = 31.0  # the lease has run out; no expire() call, no other request

    assert woken.wait(3.0), "the queued operation did not notice the ended lease"
    assert active_id(operations) == second["id"]


def test_the_newest_finished_result_survives_the_size_limit():
    """A caller that just watched a large job succeed is about to fetch it. Pruning the
    record on the way out of `finish()` turned that success into a missing artifact."""
    operations = Operations(max_bytes=1024)

    newest = operations.begin({"kind": "video"})
    operations.finish(newest["id"], VideoResult(b"x" * 4096, 8, 8, 1, 24, 7))

    assert operations.get(newest["id"])["status"] == "succeeded"
    assert operations.result(newest["id"]).mp4 == b"x" * 4096

    older = operations.begin({"kind": "video"})
    operations.finish(older["id"], VideoResult(b"y" * 4096, 8, 8, 1, 24, 7))

    # The newest one moved: the older result now gives way, and the newer one stays.
    assert operations.result(older["id"]).mp4 == b"y" * 4096
    with pytest.raises(OperationMissing):
        operations.result(newest["id"])


def test_a_cancelled_waiting_request_cannot_evict_the_run_it_waited_behind():
    """A queued request that is cancelled gets a finish time without ever running. The
    newest-result protection used to read that finish time as the newest completion, so
    the large result that had just succeeded was the one pruned."""
    operations = Operations(max_queue=1, max_bytes=1024)
    running = operations.begin({"kind": "video"})
    waiting = operations.begin({"kind": "video"}, queued=True)

    assert operations.stopping(waiting["id"])["status"] == "cancelled"
    operations.finish(running["id"], VideoResult(b"x" * 4096, 8, 8, 1, 24, 7))

    assert operations.result(running["id"]).mp4 == b"x" * 4096
    with pytest.raises(OperationMissing):
        operations.get(waiting["id"])


def test_the_protected_result_does_not_depend_on_the_clock():
    """Two finishes in one tick are not ordered by their timestamps. The protection holds
    because only a record that kept a result can be newest, and one operation runs at a
    time, so the clock has nothing to decide."""
    operations = Operations(max_queue=1, max_bytes=1024, clock=lambda: 0.0)
    running = operations.begin({"kind": "video"})
    waiting = operations.begin({"kind": "video"}, queued=True)

    operations.stopping(waiting["id"])
    operations.finish(running["id"], VideoResult(b"x" * 4096, 8, 8, 1, 24, 7))

    assert operations.result(running["id"]).mp4 == b"x" * 4096


def test_model_control_waits_for_a_queue_that_holds_the_slot():
    """Between one run ending and the head of the queue claiming the slot there is no
    active operation, and the slot is still spoken for. A model switch or an asset
    deletion there would free or delete what the queued run is about to load."""
    operations = Operations(max_queue=1)
    first = operations.begin({"kind": "image"})
    queued = operations.begin({"kind": "image"}, queued=True)
    operations.finish(first["id"], {})

    assert operations.active() is None
    assert operations.busy()
    with pytest.raises(BackendBusy):
        operations.exclusive(lambda: None)

    operations.wait_for_turn(queued["id"])
    operations.finish(queued["id"], {})

    assert not operations.busy()
    operations.exclusive(lambda: None)


def test_closing_admission_cancels_the_queue_and_leaves_the_run_in_flight():
    """Shutdown stops the run in flight, and that run's finish() wakes the head of the
    queue. Nothing may take the slot while the models and the storage are being released."""
    operations = Operations(max_queue=2)
    running = operations.begin({"kind": "video"})
    first = operations.begin({"kind": "video"}, queued=True)
    second = operations.begin({"kind": "video"}, queued=True)

    operations.close_admission()

    assert operations.get(running["id"])["status"] == "running"
    assert operations.get(first["id"])["status"] == "cancelled"
    assert operations.get(second["id"])["status"] == "cancelled"
    assert operations.queue_position(first["id"]) is None
    with pytest.raises(BackendBusy, match="stopping"):
        operations.begin({"kind": "image"})
    with pytest.raises(BackendBusy, match="stopping"):
        operations.begin({"kind": "image"}, queued=True)
    assert operations.busy()


def test_a_queued_waiter_ends_when_admission_closes():
    operations = Operations(max_queue=1)
    operations.begin({"kind": "video"})
    waiting = operations.begin({"kind": "video"}, queued=True)
    outcome = []

    def wait():
        try:
            operations.wait_for_turn(waiting["id"])
        except Cancelled as error:
            outcome.append(str(error))

    thread = threading.Thread(target=wait)
    thread.start()
    operations.close_admission()
    thread.join(2)

    assert outcome == ["The operation was cancelled before it started."]
    assert operations.get(waiting["id"])["status"] == "cancelled"


def test_abandon_ends_a_queued_operation_without_taking_the_active_slot():
    """A request is reserved before its worker thread exists. A thread that cannot start
    leaves nothing that would finish the operation."""
    operations = Operations(max_queue=1)
    running = operations.begin({"kind": "image"})
    queued = operations.begin({"kind": "image"}, queued=True)

    operations.abandon(queued["id"], RuntimeError("no thread"))

    assert operations.get(queued["id"])["status"] == "failed"
    assert "no thread" in operations.get(queued["id"])["error"]
    assert operations.queue_position(queued["id"]) is None
    assert active_id(operations) == running["id"]


def test_abandon_ends_the_active_operation_that_never_got_a_worker():
    operations = Operations()
    running = operations.begin({"kind": "image"})

    operations.abandon(running["id"], RuntimeError("no thread"))

    assert operations.get(running["id"])["status"] == "failed"
    assert operations.active() is None
    second = operations.begin({"kind": "image"})
    assert active_id(operations) == second["id"]


def test_the_queue_refuses_more_media_than_its_budget():
    """The GPU runs one request at a time. Without a byte budget the queue is where a
    series of pushed clips fills memory before any work starts."""
    operations = Operations(max_queue=2, max_queue_bytes=100)
    operations.begin({"kind": "image"})
    operations.begin({"kind": "image", "payload_bytes": 60}, queued=True)

    with pytest.raises(QueueFull, match="too much media"):
        operations.begin({"kind": "image", "payload_bytes": 60}, queued=True)

    operations.begin({"kind": "image", "payload_bytes": 40}, queued=True)
    assert operations.queueing()


def test_a_negative_queue_byte_budget_is_refused():
    with pytest.raises(ValueError, match="max_queue_bytes"):
        Operations(max_queue_bytes=-1)


def test_the_queue_pressure_reads_what_waits_without_moving_it():
    """An operator reads this from the state poll. It counts the waiting requests, the
    media they hold, and the ones whose turn has not been decided yet."""
    operations = Operations(max_queue=2, max_queue_bytes=1000)
    operations.begin({"kind": "image", "payload_bytes": 500})
    waiting = operations.begin({"kind": "video", "payload_bytes": 300}, queued=True)
    operations.begin({"kind": "video", "payload_bytes": 200}, queued=True)

    pressure = operations.pressure()

    assert pressure == {
        "queued": 2,
        "pending_admissions": 2,
        "queued_bytes": 500,
        "max_queued": 2,
        "max_queued_bytes": 1000,
    }
    assert operations.queue_position(waiting["id"]) == 1


def test_private_results_are_bounded_by_the_disk_budget(tmp_path):
    """The gateway hands the budget to the encrypted store, so the oldest private result
    goes before the disk fills. The record stays, and its result reads as missing."""
    key = "a private random caller key of at least 32 characters"
    operations = Operations(private_directory=tmp_path, private_max_bytes=4096)
    ids = []
    for _ in range(3):
        operation = operations.begin({"kind": "voice", "owner": "digest", "prompt": ""}, private_key=key)
        operations.finish(
            operation["id"],
            SpeechResult(wav=b"x" * 1600, seconds=1.0, sample_rate=16000, seed=1, steps=1),
        )
        ids.append(operation["id"])

    assert operations._private_results.total_size() <= 4096
    assert operations.get(ids[0])["result_retained"] is True  # the record stays
    with pytest.raises(OperationMissing):
        operations.result(ids[0], key)
    assert operations.result(ids[-1], key).wav
    operations.close()
