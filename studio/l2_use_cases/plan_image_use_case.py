"""What an image run would do, without running it.

A program that plans a queue asks this before it runs anything. It gets the run's own checks,
the settings that the run would take with every default filled in, and the time. It reads the
named backend's form and its mode's constants only, so it loads no weights, takes no lock and
leaves the active backend as it is. It answers while a run holds the engine.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.image_estimate import ImageEstimate, estimate_image
from studio.l1_entities.image_job import OptionValue
from studio.l1_entities.lora import LoraUse
from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway


@dataclass(frozen=True)
class PlanImageRequest:
    mode: str
    options: Mapping[str, str]  # raw form values, checked against the mode as a run checks them
    reference_sizes: tuple[tuple[int, int], ...] = field(default=())  # (width, height) of each reference
    total: int = 1  # the count: the images of the run, or of each reference with each_reference
    backend: str = ""  # blank asks about the active backend
    each_reference: bool = False
    mask: bool = False  # the last reference is the region mask
    seed: str = ""  # blank draws one at the run


@dataclass(frozen=True)
class PlanImageResponse:
    backend: str
    mode: str
    count: int
    """The images that the request makes."""
    effective_options: dict[str, OptionValue]
    """Every setting of the mode, as the run would take it."""
    loras: tuple[LoraUse, ...]
    offers_loras: bool
    estimate: ImageEstimate


class PlanImageUseCase:
    def __init__(self, catalog: BackendCatalogGateway):
        self._catalog = catalog

    def execute(self, request: PlanImageRequest) -> PlanImageResponse:
        """The run's own checks first, so a request that a run would refuse gets no plan: the
        backend is one the page offers, the mode is its own, the references fit, the count fits,
        the seed is a whole number and every setting parses."""
        backend_id = request.backend or self._catalog.active_id()
        if backend_id not in self._catalog.visible_ids():
            raise InvalidJob(f"No image model is offered as {backend_id}.")
        capabilities = self._catalog.get(backend_id).capabilities()
        mode = capabilities.mode(request.mode)
        mode.check_references(len(request.reference_sizes))
        # The count means what a run means by it, so the limit is the run's own.
        each = request.each_reference and mode.each_reference and not request.mask
        limit = capabilities.max_batch * (len(request.reference_sizes) if each else 1)
        if not 1 <= request.total <= limit:
            raise InvalidJob(f"count must be between 1 and {limit}")
        if request.seed.strip() and not request.seed.strip().isdigit():
            raise InvalidJob("seed must be a whole number")
        options = mode.parse_options(request.options)
        loras = mode.parse_loras(request.options.get("loras"))
        images = request.total * (len(request.reference_sizes) if each else 1)
        estimate = estimate_image(mode, options, request.reference_sizes, images, each=each, mask=request.mask)
        return PlanImageResponse(backend_id, mode.id, images, options, loras, bool(mode.loras), estimate)
