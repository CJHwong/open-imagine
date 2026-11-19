"""What Qwen-Image-2.1 offers when it runs on a CUDA GPU.

The same checkpoints as `qwen21` and `qwen21_turbo`, on a different engine. The form is
the shared Qwen form, with the differences this engine forces.

Both modes run the same checkpoint and the same pipeline. The 2.1 pipeline conditions on
images itself: the Qwen3-VL text encoder reads them as vision context and the VAE
prepends their latents to the noise, so an edit needs no second checkpoint. Generate
takes no reference, so it has no Match option; Edit takes one to ten.

Edit runs the Turbo eight-step schedule and the model's own guidance of 1, because the
checkpoint is distilled and the pipeline is the same one.

Edit offers no Looks and no templates. AGENTS.md step 5 keeps them off until they are
sampled on this engine's path, and the Looks were sampled through the MLX engine.
"""

from dataclasses import replace

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
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
#
# The measured cost, DGX Spark GB10, bf16 weights, eight steps, guidance 1, one operation
# at a time through the studio API on 2026-11-15. Warm runs, one run of each size unless the
# count says otherwise:
#
#   Generate   512x512 3.0 (2)   768x768 7.0 (2)   1024x1024 12.0 (2)   1328x1328 19.1
#   Edit       512 out, 1 ref 4.1 (2)   2 refs 4.2   4 refs 6.4   1344 out, 1 ref 28.2
#
# A line through the generate points gives 1.466 s per step at one megapixel with the pixel
# count to the power 0.91 and no fixed cost. It reads 3.3, 6.9, 11.7 and 19.2 s, so the worst
# error is 0.3 s. A free intercept reaches -1.6 s, which a request cannot pay, and gains 0.2 s
# of fit.
#
# The edit points hold two sizes and three reference counts. The line through the two sizes
# has a fixed cost of 0.21 s at an exponent of 1.0. The 0.91 of the generate fit would make
# that fixed cost -1.6 s, and the two sizes cannot separate the two, so the simpler exponent
# stands. One more reference reads as 0.17 times the step cost: the 4-reference point alone
# gives 0.19 and the 2-reference point 0.03, and the middle value reads 4.8 and 6.2 s against
# 4.2 and 6.4 s.
#
# An NVFP4 build was measured on 2026-11-15 and its entry was dropped the same day: it ran
# 512 3.0, 768 6.0, 1024 11.0, 1328 18.1, and an edit at 512 out in 3.1 and at 1344 out in
# 25.2. That is 5 to 14% for visible grain and 4.7 GiB of memory, which does not pay. The
# rows are in docs/reference/measured-memory-and-time.md.
#
# Refit on 2026-11-19 once the transformer was compiled, from warm studio runs: generate 512
# 2.3, 768 5.1, 1024 9.0, 1328 15.4 s; edit 1024 out with 1, 2, 4, 8 and 10 references 12.5,
# 15.8, 22.6, 37.6 and 46.2 s, 512 out 2.7, 768 out 7.3, 1344 out 22.8 s. Generate reads within
# 0.1 s, edit within 1.5 s. The figures are a guide, not a promise.
GENERATE_ESTIMATE = Estimate(1.056, 1.033, 0.183, overhead_per_image=True)
EDIT_ESTIMATE = Estimate(1.503, 1.093, 0.0, overhead_per_image=True, per_reference=0.281)


TURBO_GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, TURBO_STEPS, GUIDANCE, NEGATIVE),
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
    looks=GENERATE_LOOKS,
    templates=GENERATE_TEMPLATES,
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
)


def qwen21_cuda_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="qwen21_turbo_cuda",
        name="Qwen-Image-2.1-Turbo",
        badge=badge,
        modes=(
            replace(TURBO_GENERATE, estimate=GENERATE_ESTIMATE),
            replace(TURBO_EDIT, estimate=EDIT_ESTIMATE),
        ),
        max_batch=MAX_BATCH,
        description="Qwen's own accelerated checkpoint on an NVIDIA GPU: eight steps for generation and edits with up to 10 references. Runs on CUDA.",
    )
