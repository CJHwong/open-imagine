import os

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.image.krea2.krea2_backend_gateway import Krea2BackendGateway
from studio.l3_interface_adapters.gateways.image.krea2.krea2_model import Krea2Model, missing_files
from tests.support.images import png

MODEL_DIR = os.path.expanduser("~/Library/Caches/models/krea-2-turbo-mflux-q8")


def job(references=(), **options):
    defaults = {"size": "512x512", "steps": 8, "strength": 0.4}
    return ImageJob(
        mode="generate", prompt="a red pear on a table", seed=5, options={**defaults, **options}, references=references
    )


@pytest.mark.live
@pytest.mark.skipif(bool(missing_files(MODEL_DIR)), reason="no complete local Krea 2 Turbo q8")
def test_live_text_then_reference_then_cancel():
    backend = Krea2BackendGateway(Krea2Model(MODEL_DIR))
    steps = []
    result = backend.run(job(), lambda step, total: steps.append((step, total)), lambda: False)
    assert (result.width, result.height) == (512, 512)
    assert steps == [(step, 8) for step in range(9)]

    # Strength 0.5 skips int(8 * 0.5) = 4 steps, and the page counts the 4 that run.
    steps.clear()
    reference = png(512, 384)
    started = backend.run(
        job(references=(reference,), size="match", strength=0.5), lambda s, t: steps.append((s, t)), lambda: False
    )
    assert started.width / started.height == pytest.approx(512 / 384, rel=0.02)
    assert steps == [(0, 8)] + [(step, 4) for step in range(1, 5)]

    steps.clear()
    with pytest.raises(Cancelled, match="stopped at step 2"):
        backend.run(job(), lambda s, t: steps.append((s, t)), lambda: len(steps) > 1)
    backend.release()
