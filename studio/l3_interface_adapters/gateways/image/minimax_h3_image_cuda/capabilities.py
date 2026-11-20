"""MiniMax H3-Image on a CUDA GPU: six fixed steps, generation and edits.

The sizes and the step count are the model's, copied from the MLX backend's table because
a backend may not import another backend. The pipeline conditions on reference images
itself: passing `image` runs its image-conditioned blocks, which resize the references for
the vae and for the text encoder, and the prompt names them `<Picture 1>`, `<Picture 2>`.
So an edit needs no second checkpoint and no second load.

No Looks or templates are offered yet: the MLX verdicts were sampled through that engine,
and this one has not re-sampled them.
"""

from dataclasses import replace

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec

# The engine takes sides that are multiples of 32, from 256 to 4096.
GRID = 32
SIZES = (
    ("1024 x 1024", 1024, 1024),
    ("2048 x 2048", 2048, 2048),
    ("1024 x 576 (16:9)", 1024, 576),
    ("1536 x 864 (16:9)", 1536, 864),
    ("2560 x 1440 (16:9)", 2560, 1440),
    ("576 x 1024 (9:16)", 576, 1024),
    ("864 x 1536 (9:16)", 864, 1536),
    ("1440 x 2560 (9:16)", 1440, 2560),
    ("1152 x 864 (4:3)", 1152, 864),
    ("2304 x 1728 (4:3)", 2304, 1728),
    ("864 x 1152 (3:4)", 864, 1152),
    ("1728 x 2304 (3:4)", 1728, 2304),
)
SIZE = ParamSpec("size", "choice", "1024x1024", choices=tuple(Choice(f"{w}x{h}", label) for label, w, h in SIZES))
# The checkpoint is distilled to six steps and the engine has no other schedule.
STEP_COUNT = 6
STEPS = ParamSpec("steps", "number", STEP_COUNT, minimum=STEP_COUNT, maximum=STEP_COUNT, integer=True, step=1)

MATCH = "match"
EDIT_SIZE = ParamSpec(
    "size",
    "choice",
    MATCH,
    match_first_reference_dimensions=True,
    choices=(
        *(Choice(f"{w}x{h}", label) for label, w, h in SIZES),
        Choice(MATCH, "Match first reference dimensions (256 to 4096 per side, up to 4 MP, 4:1)"),
    ),
)
# The engine takes 16. Do not advertise more than the measurement reached.
MAX_REFERENCES = 4

# DGX Spark, Studio API, resident child, six steps. One request per case. Reference edits use
# one 512 x 512 image; the four-reference run repeats that image. Times include polling. fp8
# was measured on 2026-11-19 with fp8 matrix multiplies (W8A8), NVFP4 on 2026-11-16. Each
# estimate fits a cost, a growth with area and a fixed cost through the three areas.
#                         1024 x 576  1024 x 1024  2048 x 2048  4 refs at 1024
# FP8 generate               4.03 s        6.55 s       30.35 s       --
# FP8 edit                  18.51 s       20.73 s       57.59 s     94.48 s
# NVFP4 generate            19.36 s       21.15 s       34.30 s       --
# NVFP4 edit                29.51 s       31.26 s       44.29 s     64.79 s
# Reference size also affects encoding time; these estimates are only a starting point.
# The fp8 edit was refit on 2026-11-19 as an average over twelve runs, adding: 2048 out with one
# reference at 1024, 1536 and 2048 took 55.5, 68.8 and 88.5 s, four at 2048 349.2 s; 1024 out
# with one at 2048 59.5 s and two at 2048 114.3 s. The engine reads each reference with its short
# edge between 1024 and 2048, and that cost follows the reference, not the output, so a large
# reference with a small output reads up to 58% low. The common cases read within about 25%.
FP8_GENERATE_ESTIMATE = Estimate(0.756, 1.284, 1.73, overhead_per_image=True)
FP8_EDIT_ESTIMATE = Estimate(2.067, 0.969, 12.133, overhead_per_image=True, per_reference=2.032)
NVFP4_GENERATE_ESTIMATE = Estimate(0.693, 1.0, 16.86, overhead_per_image=True)
NVFP4_EDIT_ESTIMATE = Estimate(0.686, 1.0, 27.02, overhead_per_image=True, per_reference=2.584)
ESTIMATES = {
    "fp8": (FP8_GENERATE_ESTIMATE, FP8_EDIT_ESTIMATE),
    "nvfp4": (NVFP4_GENERATE_ESTIMATE, NVFP4_EDIT_ESTIMATE),
}


GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS),
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
)

EDIT = ModeSpec(
    id="edit",
    label="Edit",
    params=(EDIT_SIZE, STEPS),
    min_references=1,
    max_references=MAX_REFERENCES,
    prompt_hint="Say what to change. Name a reference as <Picture 1>, <Picture 2>, in the order you added them.",
    prompt_required="An edit instruction is required.",
)


# backend id -> what sets the build apart in the picker, which shows no badge.
DESCRIPTIONS = {
    "minimax_h3_image_cuda": "A 33B model known for close instruction following, run in FP8 for speed: six steps up to 4 MP, and edits from up to 4 references. Runs on CUDA.",
}


def minimax_h3_image_cuda_capabilities(
    backend_id: str = "minimax_h3_image_cuda", name: str = "MiniMax H3-Image", badge: str = "fp8"
) -> Capabilities:
    """The record for one build. A build no run measured takes the fp8 figures."""
    generate_estimate, edit_estimate = ESTIMATES.get(badge, ESTIMATES["fp8"])
    return Capabilities(
        backend_id=backend_id,
        name=name,
        badge=badge,
        modes=(
            replace(GENERATE, estimate=generate_estimate),
            replace(EDIT, estimate=edit_estimate),
        ),
        max_batch=1,
        description=DESCRIPTIONS.get(backend_id, DESCRIPTIONS["minimax_h3_image_cuda"]),
    )
