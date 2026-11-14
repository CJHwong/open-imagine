"""Real Qwen-Image-2.1 Turbo on a CUDA GPU. Needs the DGX Spark and its weights."""

import base64
import io
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from studio.l3_interface_adapters.gateways.image.qwen21_cuda.construction import qwen21_cuda_backend
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import assemble_studio


@pytest.mark.live
def test_live_qwen21_cuda_generates_a_picture():
    config = load_config(Path(__file__).resolve().parents[5] / "studio.toml")
    gateway = qwen21_cuda_backend(config)
    studio = assemble_studio(
        {"qwen21_turbo_cuda": gateway},
        {"qwen21_turbo_cuda": NoPromptRewriterGateway()},
        "qwen21_turbo_cuda",
        ("qwen21_turbo_cuda",),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps(
            {
                "backend": "qwen21_turbo_cuda",
                "prompt": "A red teapot on a wooden table.",
                "width": 512,
                "height": 512,
                "steps": 8,
                "seed": 7,
            }
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/v1/images/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=1800) as answer:
            payload = json.loads(answer.read())
        picture = Image.open(io.BytesIO(base64.b64decode(payload["images"][0]["png_base64"])))
        assert picture.size == (512, 512)
    finally:
        studio.shutdown()
        server.shutdown()
        thread.join()
        server.server_close()
