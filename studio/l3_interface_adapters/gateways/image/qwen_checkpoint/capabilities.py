"""What a Qwen checkpoint that a plugin names offers the page.

The controls are the family's, from `qwen_image_controls`, less the ones that were only
tried on the base model. Guidance and the negative prompt stay out, so a run is CFG 1.
Looks, templates and region marking stay out until AGENTS.md step 5 tries them on the
checkpoint. No estimate: a cost fit is measured on the checkpoint's own weights.

Generate keeps its reference and Strength on both schedules, as qwen21 offers them.
On `linear_quadratic` a reference does little: mflux starts an image-to-image run at step
`steps * strength`, and this schedule holds its sigmas near 1 for the first half, so the
default of 0.4 starts at sigma 0.98, where the shifted linear schedule starts at 0.77. A
page with no reference slot on Generate does not exist yet, so the slot stays.
"""

from dataclasses import replace

from studio.l1_entities.capabilities import Capabilities, ModeSpec
from studio.l3_interface_adapters.gateways.image.shared.qwen_image_controls import (
    MATCH,
    MAX_BATCH,
    MAX_REFERENCES,
    RESOLUTION,
    SIZE,
    STRENGTH,
    steps_param,
)
from studio.l3_interface_adapters.gateways.image.shared.qwen_schedules import SAMPLERS, SCHEDULES


def qwen_checkpoint_capabilities(
    backend_id: str,
    name: str,
    *,
    badge: str,
    description: str = "",
    scheduler: str = "linear",
    generate_sampler: str = "euler",
    steps: tuple[int, int, int] = (40, 1, 100),
    generate_size: str = "1024x1024",
    max_edit_references: int = MAX_REFERENCES,
) -> Capabilities:
    """The record for one checkpoint. A ValueError names the field that is wrong."""
    if scheduler not in SCHEDULES:
        raise ValueError(f"scheduler is {' or '.join(SCHEDULES)}, not {scheduler!r}")
    if generate_sampler not in SAMPLERS:
        raise ValueError(f"generate_sampler is {' or '.join(SAMPLERS)}, not {generate_sampler!r}")
    if generate_sampler == "euler_ancestral" and scheduler != "linear_quadratic":
        raise ValueError("generate_sampler euler_ancestral needs scheduler linear_quadratic")
    default, minimum, maximum = steps
    if not 1 <= minimum <= default <= maximum:
        raise ValueError(f"steps is (default, minimum, maximum) with 1 <= minimum <= default <= maximum, not {steps}")
    if generate_size == MATCH or generate_size not in {choice.value for choice in SIZE.choices}:
        raise ValueError(f"generate_size {generate_size!r} is not one of the Qwen sizes")
    if not 1 <= max_edit_references <= MAX_REFERENCES:
        raise ValueError(f"max_edit_references is 1 to {MAX_REFERENCES}, not {max_edit_references}")
    generate_steps = steps_param(default=default, minimum=minimum, maximum=maximum)
    # mflux refuses an edit of one step, and it does so after the edit model is built.
    edit_steps = steps_param(default=max(2, default), minimum=max(2, minimum), maximum=max(2, maximum))
    return Capabilities(
        backend_id=backend_id,
        name=name,
        badge=badge,
        modes=(
            ModeSpec(
                id="generate",
                label="Generate",
                params=(replace(SIZE, default=generate_size), generate_steps, STRENGTH),
                max_references=1,  # mflux's generate_image takes one image_path
                prompt_hint="Describe the image. Put any text you want rendered in quotes.",
            ),
            ModeSpec(
                id="edit",
                label="Edit",
                params=(RESOLUTION, edit_steps),
                min_references=1,
                max_references=max_edit_references,
                prompt_hint="For example: make it night, with the lights on",
                prompt_required="An edit instruction is required.",
                each_reference=True,
            ),
        ),
        max_batch=MAX_BATCH,
        description=description or "A Qwen-Image-2.1 checkpoint on the studio's mflux engine.",
    )
