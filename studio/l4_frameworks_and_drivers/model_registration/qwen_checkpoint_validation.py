"""Validate one public model-registration format."""

from studio.plugins import API_VERSION
from studio.plugins.qwen_checkpoint_registration import QwenCheckpointRegistration


def validate(checkpoint: QwenCheckpointRegistration, kind: str, name: str) -> None:
    if kind != "image":
        raise ValueError("a QwenCheckpointRegistration is an image model: register it under open_imagine.models.image")
    if checkpoint.api_version != API_VERSION:
        raise ValueError(f"expected QwenCheckpointRegistration API version {API_VERSION}")
    if checkpoint.backend_id != name:
        raise ValueError(f"expected a QwenCheckpointRegistration with backend_id {name!r}")
    for field in ("name", "description", "scheduler", "generate_sampler", "generate_size"):
        if not isinstance(getattr(checkpoint, field), str):
            raise ValueError(f"a QwenCheckpointRegistration's {field} must be text")
    steps = checkpoint.steps
    if not isinstance(steps, tuple) or len(steps) != 3 or not all(_whole(value) for value in steps):
        raise ValueError("a QwenCheckpointRegistration's steps must be three whole numbers: default, minimum, maximum")
    if not _whole(checkpoint.max_edit_references):
        raise ValueError("a QwenCheckpointRegistration's max_edit_references must be a whole number")


def _whole(value) -> bool:
    # bool is an int in Python, and True would pass as 1.
    return isinstance(value, int) and not isinstance(value, bool)
