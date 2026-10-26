"""Public Image plugin types; outputs cross the boundary as PNG bytes."""

from dataclasses import dataclass

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, LookRow, ModeSpec, ParamSpec, Template
from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.image_job import ImageJob, ImageResult, ReferenceImage
from studio.l1_entities.lora import Lora, LoraUse
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.plugins import API_VERSION


@dataclass(frozen=True)
class QwenCheckpoint:
    """An entry point exports this record in place of a ModelPlugin to run a Qwen-Image-2.1
    checkpoint, such as a finetune, on the studio's own engine. The host builds the model
    as it builds its own Qwen models.

    The plugin's section of the settings names the checkpoint's folder in `model_dir`, in
    the mflux layout, and its LoRAs in `[[<backend_id>.loras]]` tables. `scheduler` is
    "linear" or "linear_quadratic". `generate_sampler` is "euler", or "euler_ancestral" on
    linear_quadratic; an edit always samples Euler. `steps` is the default, the minimum
    and the maximum. Guidance stays at 1, and Looks, templates and region marking stay off,
    because none of them was tried on a finetune.
    """

    backend_id: str
    name: str
    description: str = ""
    scheduler: str = "linear"
    generate_sampler: str = "euler"
    steps: tuple[int, int, int] = (40, 1, 100)
    generate_size: str = "1024x1024"
    max_edit_references: int = 10
    api_version: int = API_VERSION


__all__ = [
    "Cancelled",
    "Capabilities",
    "Choice",
    "Estimate",
    "ImageBackendGateway",
    "ImageJob",
    "ImageResult",
    "InvalidJob",
    "LookRow",
    "Lora",
    "LoraUse",
    "ModeSpec",
    "ParamSpec",
    "QwenCheckpoint",
    "ReferenceImage",
    "Template",
]
