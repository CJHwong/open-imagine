"""Registration for weights executed by Studio's existing image runtime."""

from dataclasses import dataclass

from studio.plugins.api_version import MODEL_PLUGIN_API_VERSION


@dataclass(frozen=True)
class QwenCheckpointRegistration:
    """An entry point exports this record in place of a GatewayModelRegistration to run a Qwen-Image-2.1
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
    api_version: int = MODEL_PLUGIN_API_VERSION
