"""Real YuE2 through the Studio operation path. Requires an exclusive GPU slot."""

import io
import json
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
import soundfile

from studio.l3_interface_adapters.gateways.prompt_rewriters import NoPromptRewriter
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import assemble_studio, music_yue2_backend
from tests.support.fakes import FakeBackendGateway


@pytest.mark.live
def test_live_yue2_stereo_song_through_studio_operation():
    base = os.environ.get("STUDIO_MUSIC_LIVE_URL")
    studio = server = thread = None
    if not base:
        config = load_config(Path(__file__).resolve().parents[5] / "studio.toml")
        gateway = music_yue2_backend(config)
        studio = assemble_studio(
            {"fake": FakeBackendGateway()},
            {"fake": NoPromptRewriter()},
            "fake",
            ("fake",),
            music_backends={"yue2": gateway},
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
    payload = {
        "style": "English, warm piano pop, clear expressive vocals, acoustic piano, rounded bass, light drums, 88 BPM",
        "lyrics": "[Verse]\nMorning settles on the street\nEvery window keeps a beat\n\n[Chorus]\nCarry light along the road\nLet the quiet story grow",
        "seed": 42,
        "cot": "full",
    }
    try:
        request = urllib.request.Request(
            base + "/api/v1/music/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=1800) as response:
            samples, rate = soundfile.read(io.BytesIO(response.read()), always_2d=True)
            owner = response.headers["X-Studio-Operation"]
        assert rate == 48000 and samples.shape[1] == 2 and len(samples) > 48000
        assert np.isfinite(samples).all() and np.sqrt(np.mean(samples**2)) > 0.001
        with urllib.request.urlopen(base + "/api/v1/operations/" + owner + "/metadata") as response:
            metadata = json.load(response)
        assert metadata["score"] and metadata["seed"] == 42 and not metadata["stub"]
        details = metadata["metadata"]
        assert details["engine"] == "mlx-q8"
        assert details["ar_precision"] == "8bit" and details["generated_tokens"] > 0
        assert details["config"]["backend"] == "mlx" and details["config"]["ar_precision"] == "8bit"
    finally:
        if studio is not None:
            assert server is not None and thread is not None
            studio.shutdown()
            server.shutdown()
            thread.join()
            server.server_close()
