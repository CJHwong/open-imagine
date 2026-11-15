"""Real MiniMax H3-Image on a CUDA GPU. Needs the DGX Spark and its weights.

The load alone is about twelve minutes, so this test is the most expensive one here.
"""

import base64
import io
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.construction import (
    backend_factory,
)
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.main import assemble_studio


@pytest.mark.live
def test_live_minimax_h3_image_cuda_generates_a_picture():
    config = load_config(Path(__file__).resolve().parents[5] / "studio.toml")
    gateway = backend_factory("minimax_h3_image_cuda")(config)
    studio = assemble_studio(
        {"minimax_h3_image_cuda": gateway},
        {"minimax_h3_image_cuda": NoPromptRewriterGateway()},
        "minimax_h3_image_cuda",
        ("minimax_h3_image_cuda",),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps(
            {
                "backend": "minimax_h3_image_cuda",
                "prompt": "A red teapot on a wooden table.",
                "width": 1024,
                "height": 1024,
                "seed": 7,
            }
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/v1/images/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3600) as answer:
            payload = json.loads(answer.read())
        picture = Image.open(io.BytesIO(base64.b64decode(payload["images"][0]["png_base64"])))
        assert picture.size == (1024, 1024)
    finally:
        studio.shutdown()
        server.shutdown()
        thread.join()
        server.server_close()
