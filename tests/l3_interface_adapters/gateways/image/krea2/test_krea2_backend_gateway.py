from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.image.krea2.krea2_backend_gateway import Krea2BackendGateway


class Model:
    """The engine side, which the backend only forwards to."""

    def __init__(self):
        self.calls = []

    def load(self):
        self.calls.append("load")

    def run(self, the_job, on_step, should_stop):
        self.calls.append(("run", the_job))
        return ImageResult(png=b"png", width=8, height=8, seed=the_job.seed, steps=1)

    def release(self):
        self.calls.append("release")


def test_the_page_sees_the_krea2_form_and_its_stored_bits():
    caps = Krea2BackendGateway(None).capabilities()
    assert (caps.backend_id, caps.badge) == ("krea2", "int8")


def test_every_call_reaches_the_engine():
    model = Model()
    backend = Krea2BackendGateway(model)
    the_job = ImageJob(mode="generate", prompt="a pear", seed=5, options={"size": "16x16", "steps": 8})
    backend.load()
    result = backend.run(the_job, lambda step, total: None, lambda: False)
    backend.release()
    assert model.calls == ["load", ("run", the_job), "release"]
    assert result.steps == 1
