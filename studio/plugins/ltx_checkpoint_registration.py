"""Registration for weights executed by Studio's existing video runtime."""

from dataclasses import dataclass

from studio.plugins.api_version import MODEL_PLUGIN_API_VERSION


@dataclass(frozen=True)
class LtxCheckpointRegistration:
    """An entry point exports this record in place of a GatewayModelRegistration to run an LTX pack, such as
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
    api_version: int = MODEL_PLUGIN_API_VERSION
