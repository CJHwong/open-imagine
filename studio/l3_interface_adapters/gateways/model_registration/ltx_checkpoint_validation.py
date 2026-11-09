"""Validate one public model-registration format."""

from studio.plugins import API_VERSION
from studio.plugins.ltx_checkpoint_registration import LtxCheckpointRegistration


def validate(pack: LtxCheckpointRegistration, kind: str, name: str) -> None:
    if kind != "video":
        raise ValueError("an LtxCheckpointRegistration is a video model: register it under open_imagine.models.video")
    if pack.api_version != API_VERSION:
        raise ValueError(f"expected LtxCheckpointRegistration API version {API_VERSION}")
    if pack.backend_id != name:
        raise ValueError(f"expected an LtxCheckpointRegistration with backend_id {name!r}")
    for field in ("name", "family", "description", "precision"):
        if not isinstance(getattr(pack, field), str):
            raise ValueError(f"an LtxCheckpointRegistration's {field} must be text")
    for field in ("edit", "audio", "fast_mode"):
        if not isinstance(getattr(pack, field), bool):
            raise ValueError(f"an LtxCheckpointRegistration's {field} must be True or False")
