from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import BackendBusy
from studio.l4_frameworks_and_drivers import studio as studio_module
from studio.l4_frameworks_and_drivers.studio import Studio


def test_start_connect_without_a_transport_returns_no_phone_connection():
    studio = Studio(
        handler=Mock(), catalog=Mock(), video_catalog=None, residency=Mock(), cancel=Mock(), operations=Mock()
    )
    assert studio.start_connect() is None


def test_shutdown_closes_the_gpu_worker_after_releasing_models():
    events = []
    studio = Studio(
        handler=Mock(),
        catalog=Mock(),
        video_catalog=None,
        residency=Mock(release=lambda: events.append("models")),
        cancel=Mock(),
        operations=Mock(),
        close_gpu=lambda: events.append("worker"),
    )

    studio.shutdown()

    assert events == ["models", "worker"]


def test_shutdown_attempts_all_cleanups_and_preserves_multiple_failures():
    events = []
    model_error = RuntimeError("model release failed")
    rewrite_error = ValueError("rewriter release failed")

    def release_model():
        events.append("models")
        raise model_error

    def release_rewriter():
        events.append("rewriter")
        raise rewrite_error

    studio = Studio(
        handler=Mock(),
        catalog=Mock(),
        video_catalog=None,
        cancel=Mock(),
        residency=Mock(release=release_model),
        rewriter=Mock(release=release_rewriter),
        video_rewriter=Mock(release=lambda: events.append("video")),
        connect=Mock(stop=lambda: events.append("connect")),
        operations=Mock(close=lambda: events.append("operations")),
        close_gpu=lambda: events.append("worker"),
    )

    with pytest.raises(ExceptionGroup) as failed:
        studio.shutdown()

    assert failed.value.exceptions == (model_error, rewrite_error)
    assert events == ["models", "rewriter", "video", "connect", "operations", "worker"]


def test_shutdown_preserves_one_original_cleanup_failure():
    failure = RuntimeError("model release failed")
    closer = Mock()
    operations = Mock(active=Mock(return_value=None))
    studio = Studio(
        handler=Mock(),
        catalog=Mock(),
        video_catalog=None,
        cancel=Mock(),
        operations=operations,
        residency=Mock(release=Mock(side_effect=failure)),
        close_gpu=closer,
    )

    with pytest.raises(RuntimeError) as failed:
        studio.shutdown()

    assert failed.value is failure
    operations.close.assert_called_once()
    closer.assert_called_once()


def test_shutdown_closes_admission_before_it_stops_the_run(monkeypatch):
    """A queued request wakes when the run in flight finishes. Admission has to be closed
    first, or that wake takes the slot while models and storage are being released."""
    events = []
    operations = Mock()
    operations.active.side_effect = [{"id": "op", "status": "running"}, None]
    operations.close_admission = lambda: events.append("closed")
    operations.stopping = lambda operation_id: events.append(f"stopped {operation_id}")
    studio = Studio(
        handler=Mock(), catalog=Mock(), video_catalog=None, residency=Mock(), cancel=Mock(), operations=operations
    )

    studio.shutdown()

    assert events == ["closed", "stopped op"]


def test_shutdown_stops_the_run_in_flight_and_waits_for_it_to_end():
    """A video run reads the cancel through the operation's own status, and its MLX
    release frees nothing. Without the stop and the wait, the child outlives the server."""
    operations = Mock()
    operations.active.side_effect = [
        {"id": "op", "status": "running"},
        {"id": "op", "status": "stopping"},
        None,
    ]
    studio = Studio(
        handler=Mock(), catalog=Mock(), video_catalog=None, residency=Mock(), cancel=Mock(), operations=operations
    )

    studio.shutdown()

    operations.stopping.assert_called_once_with("op")
    operations.close.assert_called_once()


def test_shutdown_tolerates_a_run_that_ends_before_it_can_be_stopped():
    operations = Mock()
    operations.active.return_value = {"id": "op", "status": "running"}
    operations.stopping.side_effect = BackendBusy("This operation is no longer active.")
    studio = Studio(
        handler=Mock(), catalog=Mock(), video_catalog=None, residency=Mock(), cancel=Mock(), operations=operations
    )

    studio.shutdown()

    operations.close.assert_called_once()


def test_shutdown_gives_up_waiting_at_the_bound_and_still_closes(monkeypatch):
    monkeypatch.setattr(studio_module, "SHUTDOWN_WAIT_SECONDS", 0.0)
    operations = Mock()
    operations.active.return_value = {"id": "op", "status": "running"}
    studio = Studio(
        handler=Mock(), catalog=Mock(), video_catalog=None, residency=Mock(), cancel=Mock(), operations=operations
    )

    studio.shutdown()

    operations.stopping.assert_called_once_with("op")
    operations.close.assert_called_once()


def test_a_second_shutdown_does_nothing_after_a_partial_cleanup_failure():
    """The first call names what failed, and the second must not touch the handles the
    first one closed or hide the original reason."""
    failure = RuntimeError("model release failed")
    operations = Mock(active=Mock(return_value=None))
    closer = Mock()
    studio = Studio(
        handler=Mock(),
        catalog=Mock(),
        video_catalog=None,
        cancel=Mock(),
        operations=operations,
        residency=Mock(release=Mock(side_effect=failure)),
        close_gpu=closer,
    )

    with pytest.raises(RuntimeError) as failed:
        studio.shutdown()

    assert failed.value is failure
    studio.shutdown()  # no exception, and nothing runs twice
    operations.close.assert_called_once()
    closer.assert_called_once()
