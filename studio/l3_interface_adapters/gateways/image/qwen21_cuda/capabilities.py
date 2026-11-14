"""What Qwen-Image-2.1 offers when it runs on a CUDA GPU.

The same checkpoints as `qwen21` and `qwen21_turbo`, on a different engine. The form is
the shared Qwen form, with two differences this engine forces: Generate only, because the
edit path has not been run here yet, and no time estimate, because no run has been
measured on this engine. A mode with no estimate shows no time rather than a number
borrowed from another engine's weights.
"""

from studio.l1_entities.capabilities import Capabilities, Choice, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.image.qwen_runtime.prompt_aids import (
    GENERATE_LOOKS,
    GENERATE_TEMPLATES,
)
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_controls import (
    MAX_BATCH,
    NEGATIVE,
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

# The Turbo checkpoint samples eight steps on its own schedule.
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


def qwen21_cuda_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="qwen21_turbo_cuda",
        name="Qwen-Image-2.1-Turbo (CUDA)",
        badge=badge,
        modes=(TURBO_GENERATE,),
        max_batch=MAX_BATCH,
        description="Fast image generation in eight steps on an NVIDIA GPU.",
    )
