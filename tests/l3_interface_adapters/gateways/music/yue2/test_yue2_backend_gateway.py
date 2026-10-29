import base64
import io
from dataclasses import asdict
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.music_job import MusicJob
from studio.l3_interface_adapters.gateways.music.yue2.yue2_backend_gateway import Yue2BackendGateway


def wav(rate=48000, channels=2, frames=48):
    buffer = io.BytesIO()
    soundfile.write(buffer, np.zeros((frames, channels)), rate, format="WAV", subtype="FLOAT")
    return buffer.getvalue()


def test_load_checks_both_weights_and_release_is_idempotent(tmp_path):
    child = Mock()
    for path in ("", str(tmp_path)):
        gateway = Yue2BackendGateway(child, path, str(tmp_path))
        with pytest.raises(InvalidJob, match="model_dir"):
            gateway.load()
    for name in (
        "ar-8bit.safetensors",
        "ar-bf16.safetensors",
        "nar-bf16.safetensors",
        "conversion.json",
        "qwen.tiktoken",
        "config.json",
        "model.safetensors",
    ):
        (tmp_path / name).touch()
    gateway = Yue2BackendGateway(child, str(tmp_path), "")
    with pytest.raises(InvalidJob, match="vae_dir"):
        gateway.load()
    gateway = Yue2BackendGateway(child, str(tmp_path), str(tmp_path))
    assert gateway.capabilities().backend_id == "yue2"
    gateway.load()
    child.wait_ready.assert_called_once()
    gateway.release()
    gateway.release()
    assert child.stop.call_count == 2


def test_mlx_load_requires_converted_q8_and_bf16_conditioning_weights(tmp_path):
    child = Mock()
    vae = tmp_path / "vae"
    vae.mkdir()
    for name in ("model.safetensors", "config.json"):
        (vae / name).touch()
    gateway = Yue2BackendGateway(child, str(tmp_path), str(vae))
    assert gateway.capabilities().badge == "Q8 AR / BF16 audio"
    assert gateway.capabilities().name == "YuE2 (MLX Q8)"
    for name in (
        "ar-8bit.safetensors",
        "ar-bf16.safetensors",
        "nar-bf16.safetensors",
        "conversion.json",
        "qwen.tiktoken",
        "config.json",
    ):
        with pytest.raises(InvalidJob, match="model_dir"):
            gateway.load()
        (tmp_path / name).touch()
    gateway.load()
    child.wait_ready.assert_called_once()


def test_maps_composition_to_engine_and_preserves_stereo():
    child = Mock()
    raw = wav()
    child.request.return_value = {"wav": base64.b64encode(raw).decode(), "score": "X:1", "metadata": {"timing": 1}}
    job = MusicJob("piano", "[Verse]\nhello", 42, "melody", "X:1")
    gateway = Yue2BackendGateway(child, "", "")
    step, stop = Mock(), Mock(return_value=False)
    result = gateway.run(job, step, stop)
    child.request.assert_called_once_with({**asdict(job), "reference_audio": ""}, step, stop)
    assert result.wav == raw and result.seconds == 0.001 and result.score == "X:1" and result.seed == 42
    assert result.metadata == {"timing": 1}
    with pytest.raises(Cancelled):
        gateway.run(job, step, lambda: True)
    child.request.return_value = {"truncated": {"abc": True}}
    with pytest.raises(InvalidJob, match="generation limit"):
        gateway.run(job, step, stop)


@pytest.mark.parametrize("raw", [wav(rate=24000), wav(channels=1), wav(frames=0)])
def test_rejects_wrong_rate_channels_or_empty_audio(raw):
    child = Mock()
    child.request.return_value = {"wav": base64.b64encode(raw).decode()}
    with pytest.raises(InvalidJob, match="48 kHz stereo"):
        Yue2BackendGateway(child, "", "").run(MusicJob("a", "b", 1), Mock(), lambda: False)


@pytest.mark.parametrize("mode", ["plan", "transcribe"])
def test_score_workflows_preserve_notation_without_decoding_fake_audio(mode):
    child = Mock()
    child.request.return_value = {"score": "X:1\nK:C\nC4|", "metadata": {"mode": mode}}
    job = MusicJob("piano", "hello", 1, mode=mode, reference_audio=b"audio")
    result = Yue2BackendGateway(child, "", "").run(job, Mock(), lambda: False)
    assert result.wav == b"" and result.seconds == 0 and result.sample_rate == 48000
    assert result.score.endswith("C4|") and result.metadata == {"mode": mode}
    assert child.request.call_args.args[0]["reference_audio"] == base64.b64encode(b"audio").decode()
    child.request.return_value = {"score": "   "}
    with pytest.raises(InvalidJob, match="composition score"):
        Yue2BackendGateway(child, "", "").run(job, Mock(), lambda: False)
