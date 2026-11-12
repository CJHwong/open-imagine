"""One opt-in product-path render. Run only after releasing the shared GPU."""

import io
import os
import shutil
import socket
import subprocess
import wave
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from studio.l3_interface_adapters.gateways.video.minimax_h3.construction import minimax_h3_backend
from studio.l3_interface_adapters.gateways.video.minimax_h3.media import decode_audio, inspect_mp4
from studio.l3_interface_adapters.gateways.video.minimax_h3.runtime import DEFAULT_ENGINE, DEFAULT_MODELS, weights_ready
from studio.l4_frameworks_and_drivers.config import Config
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner
from studio.plugins.video import VideoAudio, VideoBackendGateway, VideoJob, VideoReference

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        shutil.which("uv") is None
        or not (Path(DEFAULT_ENGINE).expanduser() / "scripts/generate_staged.py").is_file()
        or not weights_ready(Path(DEFAULT_MODELS).expanduser()),
        reason="Install uv, the pinned H3 engine source and complete local weights first.",
    ),
    pytest.mark.skipif(os.environ.get("STUDIO_H3_LIVE") != "1", reason="Set STUDIO_H3_LIVE=1 with the GPU free."),
]


@contextmanager
def free_gpu():
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", 8765)) != 0, "Stop the Studio on port 8765 before a live H3 check."
    token = Path("/tmp/open-imagine-h3-gpu.token")
    descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        token.unlink()


def test_minimax_h3_renders_one_short_clip_with_real_weights():
    with free_gpu():
        steps = []
        gateway = minimax_h3_backend(Config("", (), "", (), {}), execute_process=SubprocessRunner().execute)
        assert isinstance(gateway, VideoBackendGateway)
        result = gateway.run(
            VideoJob(
                "A red fox walks through a quiet green meadow. A fixed camera. Birds sing softly.", 512, 288, 73, 24, 7
            ),
            lambda step, total, seed: steps.append((step, total, seed)),
        )
        assert result.mp4 is not None
        streams = inspect_mp4(result.mp4)
        assert steps == [(step, 8, 7) for step in range(1, 9)]
        assert {stream["codec_type"] for stream in streams} == {"video", "audio"}
        artifact = os.environ.get("STUDIO_H3_ARTIFACT_DIR")
        if artifact:
            folder = Path(artifact)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "minimax-h3-live.mp4").write_bytes(result.mp4)


def still(sun_x):
    """A sunset with the sun at `sun_x`, so the first and the last frame differ in one place."""
    image = Image.new("RGB", (512, 288), (40, 60, 140))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 200, 512, 288), fill=(20, 90, 40))
    draw.ellipse((sun_x - 30, 70, sun_x + 30, 130), fill=(250, 200, 60))
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue(), np.asarray(image, dtype=np.float32)


def test_minimax_h3_follows_a_first_and_a_last_frame_and_a_track_with_real_weights():
    first, first_pixels = still(120)
    last, last_pixels = still(390)
    seconds = np.arange(4 * 32000) / 32000
    tone = (0.3 * np.sin(2 * np.pi * 220 * seconds) * (seconds % 1 < 0.5)).astype(np.float32)
    track = io.BytesIO()
    with wave.open(track, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(32000)
        writer.writeframes((tone * 32767).astype("<i2").tobytes())
    with free_gpu():
        gateway = minimax_h3_backend(Config("", (), "", (), {}), execute_process=SubprocessRunner().execute)
        assert isinstance(gateway, VideoBackendGateway)
        result = gateway.run(
            VideoJob(
                "A yellow sun moves slowly across an evening sky above a green hill. A fixed camera.",
                512,
                288,
                73,
                24,
                11,
                (VideoReference("first.png", first, 0, 1.0), VideoReference("last.png", last, 72, 1.0)),
                audio=VideoAudio(track.getvalue(), "pulse.wav"),
            )
        )
    assert result.mp4 is not None
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", "pipe:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        input=result.mp4,
        capture_output=True,
        check=True,
    ).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, 288, 512, 3).astype(np.float32)

    def psnr(a, b):
        return 10 * np.log10(255**2 / np.mean((a - b) ** 2))

    assert psnr(frames[0], first_pixels) > psnr(frames[0], last_pixels) + 2
    assert psnr(frames[-1], last_pixels) > psnr(frames[-1], first_pixels) + 2

    def envelope(samples):
        return np.sqrt((samples[: 3 * 32000].reshape(-1, 320) ** 2).mean(axis=1))

    # The clip carries the track itself, so its loudness follows the half-second pulses. The AAC
    # encoder puts 1024 samples of its own silence in front, so the comparison skips them.
    sound = decode_audio(result.mp4, 32000)[0]
    assert np.corrcoef(envelope(sound[1024:]), envelope(tone))[0, 1] > 0.99
