"""Small opt-in smoke test through the owned stage children and the local weights."""

import io
from pathlib import Path

import pytest
from PIL import Image, ImageStat

from studio.l1_entities.image_job import ImageJob, ReferenceImage
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.minimax_h3_image_backend_gateway import (
    MinimaxH3ImageBackendGateway,
)
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

MODEL_DIR = Path.home() / "Library/Caches/models/minimax-h3-image"


@pytest.mark.live
@pytest.mark.skipif(not MODEL_DIR.is_dir(), reason="MiniMax H3-Image weights are not installed")
def test_real_generate_and_reference_edit():
    backend = MinimaxH3ImageBackendGateway(str(MODEL_DIR), SubprocessRunner().execute)
    references = ()
    for mode, size, expected, prompt in [
        ("generate", "1024x576", (1024, 576), "A red ceramic teapot on a pale wooden table, soft daylight."),
        ("edit", "match", (2720, 1536), "Make the teapot in <Picture 1> blue. Keep the table and the light."),
    ]:
        progress = []
        result = backend.run(
            ImageJob(mode, prompt, 7, {"size": size, "steps": 6}, references),
            lambda *values, progress=progress: progress.append(values),
            lambda: False,
        )
        with Image.open(io.BytesIO(result.png)) as image:
            assert image.format == "PNG" and image.size == expected
            assert max(ImageStat.Stat(image.convert("RGB")).stddev) > 10
        assert progress == [(step, 6) for step in range(7)]
        references = (ReferenceImage(result.png, result.width, result.height),)
