import base64
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.voice_job import ReferenceAudio, SpeechJob
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.drama3_cuda_backend_gateway import Drama3CudaBackendGateway


def job(references=()):
    return SpeechJob(mode="generate", text="hello", seed=7, options={"temperature": 0.7}, references=references)


def test_a_run_sends_text_seed_options_and_the_first_reference():
    child = Mock()
    child.request.return_value = {
        "wav": base64.b64encode(b"wav").decode(),
        "seconds": 1.5,
        "sample_rate": 44100,
        "steps": 1,
    }
    gateway = Drama3CudaBackendGateway(child)

    result = gateway.run(job((ReferenceAudio(b"ref", 1.0, 44100),)), Mock(), lambda: False)

    payload = child.request.call_args.args[0]
    assert payload["text"] == "hello" and payload["seed"] == 7 and payload["temperature"] == 0.7
    assert base64.b64decode(payload["audio"]) == b"ref"
    assert (result.wav, result.seconds, result.sample_rate, result.seed, result.steps) == (b"wav", 1.5, 44100, 7, 1)


def test_a_cancelled_job_never_reaches_the_child():
    child = Mock()
    with pytest.raises(Cancelled):
        Drama3CudaBackendGateway(child).run(job(), Mock(), lambda: True)
    child.request.assert_not_called()


def test_load_and_release_drive_the_child():
    child = Mock()
    gateway = Drama3CudaBackendGateway(child)
    gateway.load()
    gateway.release()
    child.wait_ready.assert_called_once()
    child.stop.assert_called_once()
    assert gateway.capabilities().backend_id == "drama3_cuda"


def test_a_run_without_a_reference_sends_no_audio_field():
    child = Mock()
    child.request.return_value = {
        "wav": base64.b64encode(b"wav").decode(),
        "seconds": 1.0,
        "sample_rate": 44100,
        "steps": 1,
    }
    Drama3CudaBackendGateway(child).run(job(), Mock(), lambda: False)
    assert "audio" not in child.request.call_args.args[0]
