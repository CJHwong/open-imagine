"""Real YuE2 on a CUDA GPU. Needs the DGX Spark and its weights."""

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

from studio.l3_interface_adapters.gateways.music.yue2_cuda import yue2_cuda_child as child
from studio.l3_interface_adapters.gateways.music.yue2_cuda.construction import (
    DEFAULT_PACK_DIR,
    backend_factory,
)
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import assemble_studio
from tests.support.fakes import FakeBackendGateway


class Config:
    """The one section a backend factory reads, without a file on disk."""

    def __init__(self, section):
        self._section = section

    def backend(self, backend_id):
        return self._section

    def required(self, backend_id, key):
        return self._section[key]


@pytest.mark.live
def test_live_yue2_cuda_returns_a_song():
    config = load_config(Path(__file__).resolve().parents[5] / "studio.toml")
    gateway = backend_factory("yue2_cuda")(config)
    studio = assemble_studio(
        {"fake": FakeBackendGateway()},
        {"fake": NoPromptRewriterGateway()},
        "fake",
        ("fake",),
        music_backends={"yue2_cuda": gateway},
        default_music_id="yue2_cuda",
        visible_music_ids=("yue2_cuda",),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps(
            {
                "backend": "yue2_cuda",
                "mode": "generate",
                "style": "Warm acoustic piano.",
                "lyrics": "[Verse]\nQuiet road, a small light",
                "seed": 7,
            }
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/v1/music/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3600) as answer:
            samples, rate = soundfile.read(io.BytesIO(answer.read()), always_2d=True)
        assert rate == 48000 and samples.shape[1] == 2
        assert len(samples) > 48000
        assert np.isfinite(samples).all() and np.sqrt(np.mean(samples**2)) > 0.001
    finally:
        studio.shutdown()
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.live
def test_live_yue2_cuda_nvfp4_serves_the_pack():
    """The fp4 path builds a pack on first use, then sings from it.

    The pack is 1.8 GB and the build quantizes 397 layers, so this test asserts the pack it
    needs is on disk after the run rather than timing the difference.
    """
    pack_dir = Path(os.path.expanduser(DEFAULT_PACK_DIR))
    model = "m-a-p/YuE2-3B"
    gateway = backend_factory("yue2_cuda")(Config({"model": model, "quantize": "nvfp4", "pack_dir": str(pack_dir)}))
    studio = assemble_studio(
        {"fake": FakeBackendGateway()},
        {"fake": NoPromptRewriterGateway()},
        "fake",
        ("fake",),
        music_backends={"yue2_cuda": gateway},
        default_music_id="yue2_cuda",
        visible_music_ids=("yue2_cuda",),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps(
            {
                "backend": "yue2_cuda",
                "mode": "generate",
                "style": "Warm acoustic piano.",
                "lyrics": "[Verse]\nQuiet road, a small light",
                "seed": 7,
            }
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/v1/music/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3600) as answer:
            samples, rate = soundfile.read(io.BytesIO(answer.read()), always_2d=True)
        assert rate == 48000 and samples.shape[1] == 2
        assert len(samples) > 48000
        assert np.isfinite(samples).all() and np.sqrt(np.mean(samples**2)) > 0.001
        manifest = json.loads((child.pack_path(pack_dir, model) / "pack.json").read_text())
        assert manifest["model"] == model
        assert len(manifest["layers"]) > 0
    finally:
        studio.shutdown()
        server.shutdown()
        thread.join()
        server.server_close()
