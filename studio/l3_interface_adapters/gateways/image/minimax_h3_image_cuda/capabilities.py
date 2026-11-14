"""MiniMax H3-Image on a CUDA GPU: six fixed steps and no guidance.

The sizes and the step count are the model's, copied from the MLX backend's table because
a backend may not import another backend. No Looks or templates are offered yet: the MLX
verdicts were sampled through that engine, and this one has not re-sampled them.
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

GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS),
    prompt_hint="Describe the image. Put any text you want rendered in quotes.",
    estimate=None,
)


def minimax_h3_image_cuda_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="minimax_h3_image_cuda",
        name="MiniMax H3-Image (CUDA)",
        badge=badge,
        modes=(GENERATE,),
        max_batch=1,
        description="MiniMax H3-Image on an NVIDIA GPU, six steps.",
    )
