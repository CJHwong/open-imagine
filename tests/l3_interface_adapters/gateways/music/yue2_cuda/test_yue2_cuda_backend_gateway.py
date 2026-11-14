import base64
import io
import json
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.music_job import MusicJob
from studio.l3_interface_adapters.gateways.music.yue2_cuda.yue2_cuda_backend_gateway import Yue2CudaBackendGateway


def wav(rate=48000, channels=2, frames=48):
    buffer = io.BytesIO()
    soundfile.write(buffer, np.zeros((frames, channels)), rate, format="WAV", subtype="FLOAT")
    return base64.b64encode(buffer.getvalue()).decode()


def job(mode="generate"):
    return MusicJob(style="piano", lyrics="[Verse]\nhello", seed=7, mode=mode)


def test_a_generate_run_returns_the_audio_the_child_sent():
    child = Mock()
    child.request.return_value = {"wav": wav(), "score": "X:1", "metadata": {"mode": "generate"}}
    gateway = Yue2CudaBackendGateway(child)

    result = gateway.run(job(), Mock(), lambda: False)

    assert result.sample_rate == 48000 and result.wav
    assert result.score == "X:1" and result.metadata == {"mode": "generate"}


def test_a_truncated_song_is_refused():
    child = Mock()
    child.request.return_value = {"wav": wav(), "truncated": {"semantic": True}}
    gateway = Yue2CudaBackendGateway(child)

    with pytest.raises(InvalidJob, match="generation limit"):
        gateway.run(job(), Mock(), lambda: False)


def test_a_plan_returns_the_score_and_no_audio():
    child = Mock()
    child.request.return_value = {"score": "X:1", "metadata": {"mode": "plan"}}
    gateway = Yue2CudaBackendGateway(child)

    result = gateway.run(job("plan"), Mock(), lambda: False)

    assert result.wav == b"" and result.score == "X:1"


def test_a_plan_without_a_score_is_refused():
    child = Mock()
    child.request.return_value = {"score": "  "}
    gateway = Yue2CudaBackendGateway(child)

    with pytest.raises(InvalidJob, match="composition score"):
        gateway.run(job("plan"), Mock(), lambda: False)


def test_audio_that_is_not_48k_stereo_is_refused():
    child = Mock()
    child.request.return_value = {"wav": wav(rate=44100)}
    gateway = Yue2CudaBackendGateway(child)

    with pytest.raises(InvalidJob, match="finite 48 kHz stereo"):
        gateway.run(job(), Mock(), lambda: False)


def test_a_cancelled_job_never_reaches_the_child():
    child = Mock()
    gateway = Yue2CudaBackendGateway(child)

    with pytest.raises(Cancelled):
        gateway.run(job(), Mock(), lambda: True)
    child.request.assert_not_called()


def test_the_payload_the_child_receives_survives_json():
    child = Mock()
    child.request.return_value = {"wav": wav(), "score": ""}
    gateway = Yue2CudaBackendGateway(child)

    gateway.run(
        MusicJob(style="piano", lyrics="[Verse]\nhello", seed=7, reference_audio=b"\x00\x01"), Mock(), lambda: False
    )

    payload = child.request.call_args.args[0]
    assert json.dumps(payload)
    assert payload["reference_audio"] == base64.b64encode(b"\x00\x01").decode("ascii")


def test_lyrics_over_the_limit_are_refused_before_the_child_runs():
    child = Mock()
    gateway = Yue2CudaBackendGateway(child)

    with pytest.raises(InvalidJob, match="600 characters"):
        gateway.run(MusicJob(style="piano", lyrics="a" * 601, seed=7), Mock(), lambda: False)

    child.request.assert_not_called()


def test_lyrics_at_the_limit_reach_the_child():
    child = Mock()
    child.request.return_value = {"wav": wav(), "score": ""}
    gateway = Yue2CudaBackendGateway(child)

    gateway.run(MusicJob(style="piano", lyrics="a" * 600, seed=7), Mock(), lambda: False)

    child.request.assert_called_once()


def test_load_waits_for_the_child_and_release_stops_it():
    child = Mock()
    gateway = Yue2CudaBackendGateway(child)

    gateway.load()
    gateway.release()

    child.wait_ready.assert_called_once()
    child.stop.assert_called_once()
    assert gateway.capabilities().backend_id == "yue2_cuda"
