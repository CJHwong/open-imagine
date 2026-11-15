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
# An edit at 1024 x 1024 came out posterized and over-sharpened on the MLX engine; the same
# edit at 2048 x 2048 was clean. Its reference path also holds an edit at 4 MP or more, so
# Edit offers only the sizes of about 4 MP, and Match follows the first picture's aspect
# at that size.
EDIT_SIZES = tuple(size for size in SIZES if size[1] * size[2] >= 3_600_000)
EDIT_SIZE = ParamSpec(
    "size",
    "choice",
    MATCH,
    choices=(
        *(Choice(f"{w}x{h}", label) for label, w, h in EDIT_SIZES),
        Choice(MATCH, "Match first reference (about 4 MP)"),
    ),
)
# The engine takes 16. Do not advertise more than the measurement reached.
MAX_REFERENCES = 4

# The measured cost, DGX Spark GB10, six steps, one operation at a time through the studio
# API on 2026-11-15. Warm runs:
#
#   fp8      generate 1024 57.4   2048 57.3   edit, 1 ref at 4 MP 70.5
#   NVFP4    generate 1024 34.3 (2)   edit, 1 ref at 4 MP 63.7
#
# The time does not follow the request. `get_image_canvas_size` raises every request below
# 4,194,304 pixels to that canvas, and every size this form offers is at or below it, so the
# six steps run on one canvas whatever the size says. That is why the two fp8 generate rows
# agree to 0.1 s across four times the pixels, and why the step cost is zero here: the figure
# is the canvas's, not the request's. An edit adds the reference encode, 13 s at one
# reference on the fp8 build and 29 s on the pack. A second reference is unmeasured, and a
# step cost of zero cannot carry one, so the edit figure holds one reference.
#
# The pack's first run is a different matter: 527.8 s and a 104.21 GiB free-memory drop,
# because the child packs and loads 38 GB before it samples anything. After that it is
# resident and a run is 34.3 s. The fp8 pack loads in 33.4 s.
FP8_GENERATE_ESTIMATE = Estimate(0.0, 1.0, 57.3, overhead_per_image=True)
FP8_EDIT_ESTIMATE = Estimate(0.0, 1.0, 70.5, overhead_per_image=True)
NVFP4_GENERATE_ESTIMATE = Estimate(0.0, 1.0, 34.3, overhead_per_image=True)
NVFP4_EDIT_ESTIMATE = Estimate(0.0, 1.0, 63.7, overhead_per_image=True)
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


def minimax_h3_image_cuda_capabilities(
    backend_id: str = "minimax_h3_image_cuda", name: str = "MiniMax H3-Image (CUDA)", badge: str = "fp8"
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
        description="MiniMax H3-Image on an NVIDIA GPU, six steps, generation and reference edits.",
    )
