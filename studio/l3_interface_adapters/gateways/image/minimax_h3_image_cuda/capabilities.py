"""MiniMax H3-Image on a CUDA GPU: six fixed steps, generation and edits.

The sizes and the step count are the model's, copied from the MLX backend's table because
a backend may not import another backend. The pipeline conditions on reference images
itself: passing `image` runs its image-conditioned blocks, which resize the references for
the vae and for the text encoder, and the prompt names them `<Picture 1>`, `<Picture 2>`.
So an edit needs no second checkpoint and no second load.

No Looks or templates are offered yet: the MLX verdicts were sampled through that engine,
and this one has not re-sampled them.
"""

from studio.l1_entities.capabilities import Capabilities, Choice, ModeSpec, ParamSpec

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

GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS),
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
    estimate=None,
)

EDIT = ModeSpec(
    id="edit",
    label="Edit",
    params=(EDIT_SIZE, STEPS),
    min_references=1,
    max_references=MAX_REFERENCES,
    prompt_hint="Say what to change. Name a reference as <Picture 1>, <Picture 2>, in the order you added them.",
    prompt_required="An edit instruction is required.",
    estimate=None,
)


def minimax_h3_image_cuda_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="minimax_h3_image_cuda",
        name="MiniMax H3-Image (CUDA)",
        badge=badge,
        modes=(GENERATE, EDIT),
        max_batch=1,
        description="MiniMax H3-Image on an NVIDIA GPU, six steps, generation and reference edits.",
    )
