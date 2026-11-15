"""What Qwen-Image-2.1 offers when it runs on a CUDA GPU.

The same checkpoints as `qwen21` and `qwen21_turbo`, on a different engine. The form is
the shared Qwen form, with the differences this engine forces.

Both modes run the same checkpoint and the same pipeline. The 2.1 pipeline conditions on
images itself: the Qwen3-VL text encoder reads them as vision context and the VAE
prepends their latents to the noise, so an edit needs no second checkpoint. Generate
takes no reference, so it has no Match option; Edit takes one to ten.

Edit runs the Turbo eight-step schedule and the model's own guidance of 1, because the
checkpoint is distilled and the pipeline is the same one. Neither mode shows a time
estimate, because no run of either has been measured on this engine yet.

Edit offers no Looks and no templates. AGENTS.md step 5 keeps them off until they are
sampled on this engine's path, and the Looks were sampled through the MLX engine.
"""

from studio.l1_entities.capabilities import Capabilities, Choice, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.image.qwen_runtime.prompt_aids import (
    GENERATE_LOOKS,
    GENERATE_TEMPLATES,
)
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_controls import (
    MAX_BATCH,
    MAX_REFERENCES,
    NEGATIVE,
    RESOLUTION,
    steps_param,
)
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_sizes import SIZES

# No Match option: this backend takes no reference yet, and Match has nothing to match.
SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="512x512",
    choices=tuple(Choice(f"{width}x{height}", label) for label, width, height in SIZES),
)
# The same control the MLX backends offer. A negative prompt works only through true
# CFG, which needs guidance above 1 and runs two passes per step.
GUIDANCE = ParamSpec(id="guidance", kind="number", default=1.0, minimum=0, maximum=10, step=0.5, with_negative=2.5)

# The Turbo checkpoint samples eight steps on its own schedule, and it is meant to be
# sampled without guidance, so 1.0 is the default the form opens on.
TURBO_STEPS = steps_param(8, 1, 50)

# The Looks and templates were sampled on these weights through the MLX engine. Prompt
# text travels with the model, not the engine, so they are offered unchanged. AGENTS.md
# step 5 re-samples them if the engine turns out to read prompts differently.
TURBO_GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, TURBO_STEPS, GUIDANCE, NEGATIVE),
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
    looks=GENERATE_LOOKS,
    templates=GENERATE_TEMPLATES,
    estimate=None,
)


TURBO_EDIT = ModeSpec(
    id="edit",
    label="Edit",
    params=(RESOLUTION, TURBO_STEPS, GUIDANCE, NEGATIVE),
    min_references=1,
    # The family's reference limit, the same one the MLX backends offer. Several
    # references are one conditioning set for the pipeline, not one run each.
    max_references=MAX_REFERENCES,
    prompt_hint="For example: make it night, with the lights on",
    prompt_required="An edit instruction is required.",
    estimate=None,
)


def qwen21_cuda_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="qwen21_turbo_cuda",
        name="Qwen-Image-2.1-Turbo (CUDA)",
        badge=badge,
        modes=(TURBO_GENERATE, TURBO_EDIT),
        max_batch=MAX_BATCH,
        description="Image generation and reference edits on an NVIDIA GPU.",
    )
