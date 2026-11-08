from studio.l1_entities.image_job import ImageJob
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.image.krea2.capabilities import krea2_capabilities


class Krea2BackendGateway(ImageBackendGateway):
    """Krea 2 Turbo. One mflux model for text-to-image and img2img."""

    def __init__(self, model):
        self._model = model

    def capabilities(self):
        # The weights are stored at int8, and mflux runs the stored bits.
        return krea2_capabilities("int8")

    def load(self):
        self._model.load()

    def run(self, job: ImageJob, on_step, should_stop):
        return self._model.run(job, on_step, should_stop)

    def release(self):
        self._model.release()
