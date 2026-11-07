"""One opt-in product-path render. Run only after releasing the shared GPU."""

import os
import socket
from pathlib import Path

import pytest
from open_imagine_h3 import plugin
from open_imagine_h3.media import inspect_mp4

from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner
from studio.plugins import PluginContext
from studio.plugins.video import VideoBackendGateway, VideoJob

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("STUDIO_H3_LIVE") != "1", reason="Set STUDIO_H3_LIVE=1 with the GPU free."),
]


def test_minimax_h3_renders_one_short_clip_with_real_weights():
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", 8765)) != 0, "Stop the Studio on port 8765 before a live H3 check."
    token = Path("/tmp/open-imagine-h3-gpu.token")
    descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        steps = []
        gateway = plugin.create(PluginContext({}, SubprocessRunner().execute))
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
    finally:
        os.close(descriptor)
        token.unlink()
