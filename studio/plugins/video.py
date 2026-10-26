"""Public Video plugin types; outputs cross the boundary as MP4 bytes."""

from dataclasses import dataclass

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.lora import Lora, LoraUse, with_triggers
from studio.l1_entities.video_capabilities import VideoAdapter, VideoCapabilities, VideoMode, VideoShape
from studio.l1_entities.video_job import VideoAudio, VideoEdit, VideoJob, VideoReference, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.plugins import API_VERSION


@dataclass(frozen=True)
class LtxPack:
    """An entry point exports this record in place of a ModelPlugin to run an LTX pack, such as
    a finetune, on the studio's own engine. The host builds the model as it builds its own.

    `family` is "ltx25" or "ltx23", the base model that the pack's weights come from. The
    plugin's section of the settings names the pack's folder in `pack_dir`, and its LoRAs in
    `[[<backend_id>.loras]]` tables. The engine's own settings stay under `[mlx_video]`.
    `edit` offers the LTX-2.5 effects, `audio` takes an audio track, and `fast_mode` offers
    the LTX-2.5 float16 path. Each stays off until it is tried on the pack.
    """

    backend_id: str
    name: str
    family: str
    description: str = ""
    precision: str = "int8"
    edit: bool = False
    audio: bool = False
    fast_mode: bool = False
    api_version: int = API_VERSION


__all__ = [
    "Cancelled",
    "InvalidJob",
    "Lora",
    "LoraUse",
    "LtxPack",
    "VideoAdapter",
    "VideoAudio",
    "VideoBackendGateway",
    "VideoCapabilities",
    "VideoEdit",
    "VideoJob",
    "VideoMode",
    "VideoReference",
    "VideoResult",
    "VideoShape",
    "with_triggers",
]
