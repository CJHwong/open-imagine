from unittest.mock import Mock

import pytest

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
    operations = Mock()
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
