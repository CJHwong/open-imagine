"""Real Drama-3 on a CUDA GPU. Needs the DGX Spark, its weights and the pinned checkout."""

import io
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
import soundfile

from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.construction import voice_drama_cuda_backend
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import assemble_studio
from tests.support.fakes import FakeBackendGateway


@pytest.mark.live
def test_live_drama3_cuda_speaks_a_sentence():
    config = load_config(Path(__file__).resolve().parents[5] / "studio.toml")
    gateway = voice_drama_cuda_backend(config)
    studio = assemble_studio(
        {"fake": FakeBackendGateway()},
        {"fake": NoPromptRewriterGateway()},
        "fake",
        ("fake",),
        voice_backends={"drama3_cuda": gateway},
        default_voice_id="drama3_cuda",
        visible_voice_ids=("drama3_cuda",),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps(
            {
                "backend": "drama3_cuda",
                "mode": "generate",
                "text": "The blue teapot is beside the window.",
                "seed": 7,
            }
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/v1/voice/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3600) as answer:
            samples, rate = soundfile.read(io.BytesIO(answer.read()), always_2d=True)
        assert rate == 44100 and samples.shape[1] == 1
        assert len(samples) > 22050
        assert np.isfinite(samples).all() and np.sqrt(np.mean(samples**2)) > 0.001
    finally:
        studio.shutdown()
        server.shutdown()
        thread.join()
        server.server_close()
