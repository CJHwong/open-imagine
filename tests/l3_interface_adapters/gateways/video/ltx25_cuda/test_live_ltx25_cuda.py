"""Real LTX-2.5 on a CUDA GPU. Needs the DGX Spark and its weights."""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.construction import ltx25_cuda_backend
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import assemble_studio
from tests.support.fakes import FakeBackendGateway


@pytest.mark.live
def test_live_ltx25_cuda_returns_a_clip():
    config = load_config(Path(__file__).resolve().parents[5] / "studio.toml")
    gateway = ltx25_cuda_backend(config)
    studio = assemble_studio(
        {"fake": FakeBackendGateway()},
        {"fake": NoPromptRewriterGateway()},
        "fake",
        ("fake",),
        video_backends={"ltx25_cuda": gateway},
        default_video_id="ltx25_cuda",
        visible_video_ids=("ltx25_cuda",),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps(
            {
                "backend": "ltx25_cuda",
                "mode": "generate",
                "prompt": "A red sailboat crosses calm water. Fixed camera.",
                "width": 384,
                "height": 384,
                "num_frames": 25,
                "frame_rate": 24,
                "seed": 7,
            }
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/v1/videos/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3600) as answer:
            clip = answer.read()
        assert len(clip) > 1000 and clip[4:8] == b"ftyp"
    finally:
        studio.shutdown()
        server.shutdown()
        thread.join()
        server.server_close()
