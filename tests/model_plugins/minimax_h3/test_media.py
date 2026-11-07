import subprocess

import numpy as np
import pytest
from open_imagine_h3 import media


def test_memory_mux_pipes_every_frame_and_stereo_sound_without_creating_files(tmp_path, monkeypatch, media_tools):
    monkeypatch.chdir(tmp_path)
    rng = np.random.default_rng(7)
    video = rng.integers(0, 256, (17, 64, 96, 3), dtype=np.uint8)
    audio = np.zeros((2, round(17 / 24 * 32000)), dtype=np.float32)

    data = media.encode_mp4(video, 24, audio, 32000)
    streams = media.inspect_mp4(data)

    picture = next(stream for stream in streams if stream["codec_type"] == "video")
    sound = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert picture["width"] == 96 and picture["height"] == 64 and int(picture["nb_read_packets"]) == 17
    assert sound["channels"] == 2 and int(sound["sample_rate"]) == 32000
    assert not list(tmp_path.iterdir())


def test_memory_mux_requires_media_tools(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="ffmpeg"):
        media.encode_mp4(None, 24, None, 32000)
    with pytest.raises(RuntimeError, match="ffprobe"):
        media.inspect_mp4(b"invalid")
    with pytest.raises(RuntimeError, match="before H3"):
        media.check_tools()


def test_memory_probe_rejects_an_unreadable_clip(media_tools):
    with pytest.raises(RuntimeError, match="unreadable"):
        media.inspect_mp4(b"invalid")


def test_memory_mux_rejects_an_encoder_failure_and_closes_its_pipes(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/false")

    with pytest.raises(RuntimeError, match="encoding failed"):
        media.encode_mp4(np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 100)), 32000)


def test_memory_mux_closes_pipe_descriptors_when_spawn_fails(monkeypatch, media_tools):
    def fail(*_, **__):
        raise OSError("cannot start encoder")

    monkeypatch.setattr(media.subprocess, "Popen", fail)

    with pytest.raises(OSError, match="cannot start"):
        media.encode_mp4(np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 100)), 32000)


def test_memory_mux_reaps_a_timed_out_encoder(monkeypatch, media_tools):
    from unittest.mock import Mock

    process = Mock()
    process.communicate.side_effect = [subprocess.TimeoutExpired("encoder", 180), (b"", b"")]
    monkeypatch.setattr(media.subprocess, "Popen", lambda *_, **__: process)

    with pytest.raises(subprocess.TimeoutExpired):
        media.encode_mp4(np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 100)), 32000)

    process.kill.assert_called_once_with()
