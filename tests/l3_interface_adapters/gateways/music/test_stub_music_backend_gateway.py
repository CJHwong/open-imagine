import io
import wave
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.music_job import MusicJob
from studio.l3_interface_adapters.gateways.music.stub_music_backend_gateway import StubMusicBackendGateway


def test_stub_is_explicit_stereo_and_cancelable(monkeypatch):
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.music.stub_music_backend_gateway.time.sleep", lambda _: None
    )
    gateway = StubMusicBackendGateway()
    gateway.load()
    assert gateway.capabilities().channels == 2
    result = gateway.run(MusicJob("pop", "a", 7, abc="X:1"), Mock(), lambda: False)
    with wave.open(io.BytesIO(result.wav)) as audio:
        assert audio.getnchannels() == 2 and audio.getframerate() == 48000
    assert result.stub and result.score == "X:1"
    gateway.release()
    with pytest.raises(Cancelled):
        gateway.run(MusicJob("pop", "a", 7), Mock(), lambda: True)


@pytest.mark.parametrize("mode", ["plan", "transcribe"])
def test_stub_score_workflows_return_composition_without_audio(mode, monkeypatch):
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.music.stub_music_backend_gateway.time.sleep", lambda _: None
    )
    result = StubMusicBackendGateway().run(MusicJob("piano", "", 7, mode=mode), Mock(), lambda: False)
    assert result.wav == b"" and result.seconds == 0 and "V:Ins" in result.score
    assert result.metadata["mode"] == mode and result.stub
