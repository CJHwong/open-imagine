import base64
from dataclasses import replace
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.lora import LoraUse
from studio.l1_entities.video_job import VideoAudio, VideoEdit, VideoJob, VideoPicture, VideoReference
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.capabilities import FLASH_CAPABILITIES
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.minimax_h3_cuda_backend_gateway import (
    MinimaxH3CudaBackendGateway,
    clip_payload,
    flash_schedule,
)


def job(**overrides):
    return replace(VideoJob(prompt="a fox", width=512, height=288, num_frames=124, frame_rate=24, seed=7), **overrides)


def still(frame, png=b"png"):
    return VideoReference(name="still.png", png=png, frame_index=frame, strength=1.0)


def picture(png=b"png"):
    return VideoPicture(name="cast.png", png=png)


def encoded(data):
    return base64.b64encode(data).decode("ascii")


def test_text_runs_the_released_fifty_steps_and_fast_mode_twenty():
    assert clip_payload(job()) == {
        "prompt": "a fox",
        "width": 512,
        "height": 288,
        "frames": 124,
        "seed": 7,
        "steps": 50,
        "forwards": 49,
        "include_audio": True,
    }
    fast = clip_payload(job(fast_mode=True))
    assert (fast["steps"], fast["forwards"]) == (20, 19)
    assert clip_payload(job(seed=None))["seed"] == 0


def flash(**overrides):
    return clip_payload(job(**overrides), FLASH_CAPABILITIES.name, flash_schedule)


def test_flash_runs_its_six_step_grid_and_counts_six_transformer_calls():
    """Flash takes the count of transformer calls and knows only 4, 6 and 8; base diffusers
    takes sigma points, one more than the calls."""
    payload = flash()
    assert (payload["steps"], payload["forwards"]) == (6, 6)
    assert flash(pictures=(picture(),))["pictures"] == [encoded(b"png")]


def test_flash_refuses_fast_mode_and_names_itself_in_a_refusal():
    with pytest.raises(InvalidJob, match="HyperFlow H3 Flash on CUDA does not support Fast mode"):
        flash(fast_mode=True)
    with pytest.raises(InvalidJob, match="HyperFlow H3 Flash on CUDA places a still only"):
        flash(references=(still(60),))


def test_a_still_on_the_first_or_last_frame_is_that_keyframe():
    payload = clip_payload(job(references=(still(0, b"a"), still(123, b"b"))))

    assert (payload["first"], payload["last"]) == (encoded(b"a"), encoded(b"b"))
    assert "pictures" not in payload
    assert "last" not in clip_payload(job(references=(still(0),)))
    assert "first" not in clip_payload(job(references=(still(123),)))


def test_a_still_between_the_ends_is_refused_with_where_it_may_go():
    with pytest.raises(InvalidJob, match="Move the still at frame 60 to frame 0 or 123"):
        clip_payload(job(references=(still(60),)))


def test_two_stills_on_one_frame_are_refused_rather_than_one_dropped():
    with pytest.raises(InvalidJob, match="one still per frame"):
        clip_payload(job(references=(still(0, b"a"), still(0, b"b"))))


def test_a_track_turns_every_still_into_a_picture_and_carries_the_track():
    track = VideoAudio(data=b"wav", name="voice.wav")
    payload = clip_payload(job(audio=track, references=(still(60, b"a"), still(0, b"b"))))

    assert payload["audio"] == encoded(b"wav")
    assert payload["pictures"] == [encoded(b"a"), encoded(b"b")]
    assert "first" not in payload


def test_a_track_without_a_picture_is_refused_before_the_child_sees_it():
    with pytest.raises(InvalidJob, match="needs a picture with an audio track"):
        clip_payload(job(audio=VideoAudio(data=b"wav", name="voice.wav")))


def test_pictures_without_a_track_run_the_reference_workflow_in_their_order():
    payload = clip_payload(job(pictures=(picture(b"a"), picture(b"b"))))

    assert payload["pictures"] == [encoded(b"a"), encoded(b"b")]
    assert "audio" not in payload
    assert "first" not in payload


def test_pictures_with_a_track_carry_both():
    payload = clip_payload(job(pictures=(picture(b"a"),), audio=VideoAudio(data=b"wav", name="voice.wav")))

    assert (payload["pictures"], payload["audio"]) == ([encoded(b"a")], encoded(b"wav"))


def test_pictures_beside_a_keyframe_are_refused_because_the_workflows_differ():
    with pytest.raises(InvalidJob, match="pictures or keyframes, not both"):
        clip_payload(job(pictures=(picture(),), references=(still(0),)))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"edit": VideoEdit(adapter="a", strength=1.0, lora_file="", clip=b"", clip_name="c")}, "Edit"),
        ({"loras": (LoraUse("style", 1.0),)}, "LoRAs"),
    ],
)
def test_what_this_engine_cannot_run_is_refused(change, message):
    with pytest.raises(InvalidJob, match=message):
        clip_payload(job(**change))


def test_a_run_reports_steps_and_returns_the_clip():
    child = Mock()

    def request(payload, on_step, cancelled):
        on_step(1, 49)
        return {"mp4": encoded(b"mp4"), "width": 512, "height": 288, "frames": 124}

    child.request.side_effect = request
    progress = Mock()
    gateway = MinimaxH3CudaBackendGateway(child)

    result = gateway.run(job(), progress, lambda: False)

    assert (result.mp4, result.width, result.height, result.num_frames, result.seed) == (b"mp4", 512, 288, 124, 7)
    progress.assert_called_once_with(1, 49, 1)
    assert gateway.run(job()).mp4 == b"mp4"
    assert gateway.capabilities().backend_id == "minimax_h3_cuda"


def test_the_flash_gateway_offers_its_own_form_and_sends_its_own_schedule():
    child = Mock()
    child.request.return_value = {"mp4": encoded(b"mp4"), "width": 512, "height": 288, "frames": 124}
    gateway = MinimaxH3CudaBackendGateway(child, FLASH_CAPABILITIES, flash_schedule)

    gateway.run(job())

    assert gateway.capabilities().backend_id == "minimax_h3_flash_cuda"
    assert child.request.call_args.args[0]["forwards"] == 6


def test_a_cancelled_job_never_reaches_the_child():
    child = Mock()
    with pytest.raises(Cancelled):
        MinimaxH3CudaBackendGateway(child).run(job(), None, lambda: True)
    child.request.assert_not_called()


def test_load_waits_for_the_child_and_release_stops_it():
    child = Mock()
    gateway = MinimaxH3CudaBackendGateway(child)
    gateway.load()
    gateway.release()
    child.wait_ready.assert_called_once()
    child.stop.assert_called_once()
