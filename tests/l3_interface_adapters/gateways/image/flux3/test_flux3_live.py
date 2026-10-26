"""Small opt-in smoke test through the owned child and pinned local weights."""

import io
from pathlib import Path

import pytest
from PIL import Image, ImageStat

from studio.l1_entities.image_job import ImageJob, ReferenceImage
from studio.l3_interface_adapters.gateways.image.flux3.flux3_backend_gateway import Flux3BackendGateway
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

MODEL_DIR = Path.home() / "Library/Caches/models/flux3-image-klein"
PYTHON_PATH = Path.home() / "Library/Caches/models/flux3-runtime/bin/python"


@pytest.mark.live
@pytest.mark.skipif(not MODEL_DIR.is_dir() or not PYTHON_PATH.is_file(), reason="FLUX3 setup is not installed")
def test_real_generate_and_reference_edit():
    backend = Flux3BackendGateway(str(MODEL_DIR), str(PYTHON_PATH), 8, "int8", SubprocessRunner().execute)
    references = ()
    try:
        for mode, color in [("generate", "red"), ("edit", "blue")]:
            progress = []
            result = backend.run(
                ImageJob(
                    mode,
                    f"A studio product photograph of a single {color} ceramic teapot centered on a pale wooden table. "
                    "Its rounded glossy body has a curved spout to the left and a loop handle to the right. "
                    "Soft daylight enters from the left, with a plain cream wall and subtle shadows. "
                    "The entire teapot is visible in a square frame, realistic ceramic texture, no text.",
                    7,
                    {"size": "512x512", "steps": 16},
                    references,
                ),
                lambda *values, progress=progress: progress.append(values),
                lambda: False,
            )
            with Image.open(io.BytesIO(result.png)) as image:
                assert image.format == "PNG" and image.size == (512, 512)
                assert max(ImageStat.Stat(image.convert("RGB")).stddev) > 10
            assert progress[0] == (0, 16) and progress[-1] == (16, 16)
            references = (ReferenceImage(result.png, result.width, result.height),)
    finally:
        backend.release()
