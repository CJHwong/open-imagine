import base64
from dataclasses import replace
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.lora import LoraUse
from studio.l1_entities.video_job import VideoAudio, VideoEdit, VideoJob
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.ltx25_cuda_backend_gateway import (
    Ltx25CudaBackendGateway,
    clip_payload,
)


def job(**overrides):
    base = VideoJob(prompt="a fox", width=768, height=512, num_frames=97, frame_rate=24, seed=7)
    return replace(base, **overrides) if overrides else base


def test_the_payload_carries_values_and_a_step_count():
    payload = clip_payload(job())

    assert payload == {
        "prompt": "a fox",
        "width": 768,
        "height": 512,
        "frames": 97,
        "frame_rate": 24,
        "seed": 7,
        "enhance": False,
        "include_audio": True,
    }


def test_a_missing_seed_becomes_zero():
    assert clip_payload(job(seed=None))["seed"] == 0


def test_a_run_turns_the_reply_into_a_video_result():
    child = Mock()
    child.request.return_value = {
        "mp4": base64.b64encode(b"mp4").decode(),
        "width": 768,
        "height": 512,
        "frames": 97,
        "steps": 30,
    }
    gateway = Ltx25CudaBackendGateway(child)
    progress = Mock()

    result = gateway.run(job(), progress, lambda: False)

    assert (result.mp4, result.width, result.height, result.num_frames, result.frame_rate) == (b"mp4", 768, 512, 97, 24)
    assert gateway.capabilities().backend_id == "ltx25_cuda"


def test_a_cancelled_job_never_reaches_the_child():
    child = Mock()
    with pytest.raises(Cancelled):
        Ltx25CudaBackendGateway(child).run(job(), None, lambda: True)
    child.request.assert_not_called()


def test_release_stops_the_child():
    child = Mock()
    Ltx25CudaBackendGateway(child).release()
    child.stop.assert_called_once()


def test_progress_reaches_the_caller_and_a_missing_cancelled_is_allowed():
    child = Mock()

    def request(payload, on_step, should_stop):
        on_step(3, 30)
        return {"mp4": "", "width": 8, "height": 8, "frames": 2, "frame_rate": 24, "steps": 30}

    child.request.side_effect = request
    progress = Mock()

    Ltx25CudaBackendGateway(child).run(job(), progress, None)

    progress.assert_called_once_with(1, 3, 30)


def test_a_run_without_cancellation_still_reaches_the_child():
    child = Mock()
    child.request.return_value = {"mp4": "", "width": 8, "height": 8, "frames": 2, "frame_rate": 24, "steps": 30}
    Ltx25CudaBackendGateway(child).run(job(), None, None)
    child.request.assert_called_once()


def test_a_step_without_a_progress_callback_is_harmless():
    child = Mock()

    def request(payload, on_step, should_stop):
        on_step(1, 30)
        return {"mp4": "", "width": 8, "height": 8, "frames": 2, "frame_rate": 24, "steps": 30}

    child.request.side_effect = request
    Ltx25CudaBackendGateway(child).run(job(), None, lambda: False)


def test_load_waits_for_the_child_to_say_ready():
    child = Mock()
    gateway = Ltx25CudaBackendGateway(child)

    gateway.load()

    child.wait_ready.assert_called_once_with()


def test_a_keyframe_crosses_with_its_frame_index_and_strength():
    from studio.l1_entities.video_job import VideoReference

    reference = VideoReference(name="first.png", png=b"png", frame_index=0, strength=0.8)
    payload = clip_payload(job(references=(reference,)))

    assert payload["references"] == [{"png_base64": "cG5n", "frame_index": 0, "strength": 0.8}]


def test_a_run_without_keyframes_sends_no_references():
    assert "references" not in clip_payload(job())


@pytest.mark.parametrize(
    "overrides",
    [
        {"edit": VideoEdit("custom", 1.0, "", b"clip", "clip.mp4")},
        {"audio": VideoAudio(b"audio", "track.wav")},
        {"fast_mode": True},
        {"loras": (LoraUse("unsupported", 1.0),)},
    ],
)
def test_unsupported_jobs_fail_before_the_child_starts(overrides):
    child = Mock()

    with pytest.raises(InvalidJob):
        Ltx25CudaBackendGateway(child).run(job(**overrides))

    child.request.assert_not_called()


def test_a_silent_request_preserves_the_output_flag():
    assert clip_payload(job(include_audio=False))["include_audio"] is False
