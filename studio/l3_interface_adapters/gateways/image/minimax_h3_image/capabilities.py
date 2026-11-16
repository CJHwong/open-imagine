"""MiniMax H3-Image: six fixed steps, no guidance, and the prompt aids it passed here."""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec
from studio.l3_interface_adapters.gateways.image.qwen_runtime.prompt_aids import (
    EDIT_LOOKS as EDIT_LOOK_CATALOG,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime.prompt_aids import (
    pick_looks,
    pick_templates,
)
from studio.l3_interface_adapters.gateways.prompt_aids import pick_looks as pick_from_catalog

# The options that passed the sample recorded in PROMPT_EVALUATION.md, one sheet per row.
# Top-down bent the still life, "Right" wrote the word Subject in the gap, and the neon
# signs came out as invented lettering, so only two of the Camera row and one of Room for
# text are offered here.
LOOKS = pick_looks(
    {
        "Medium": ("Watercolor", "3D render", "Skeleton"),
        "Film": ("Portra 400", "Ektachrome", "Black and white"),
        "Color": ("Warm", "Cool", "Muted"),
        "Light": ("Golden hour", "Studio", "Night with neon"),
        "Camera": ("Close-up 85mm", "Wide 24mm"),
        "Room for text": ("Left",),
        "Realism": ("Real person",),
        "Portrait": ("Over the shoulder", "Candid glance"),
    }
)
# Retouch reads at 2048 and the two grade rows move the whole frame, so they stay.
EDIT_LOOKS = pick_from_catalog(
    EDIT_LOOK_CATALOG,
    {
        "Exposure": ("Brighter", "Darker"),
        "White balance": ("Cooler", "Warmer"),
        "Grade": ("Teal and orange", "Muted filmic"),
        "Lens": ("Shallow depth", "Wider view", "Telephoto"),
        "Finish": ("Film grain", "Vignette", "Halation"),
        "Retouch": ("Smooth the skin", "Brighten the eyes"),
    },
)
# This model draws lettering, so the three templates that carry words are offered.
# "Change a color or material" turned the sweater into a pot, "Alternate reality" only
# pasted the subject into a street, and "Mark a region" needs a mask this model lacks.
TEMPLATES = pick_templates(
    ("Portrait photo", "Product shot", "Landscape", "Poster with text", "Illustration", "Deadpan absurdity", "Banner")
)
EDIT_TEMPLATES = pick_templates(
    ("Replace the background", "Add text", "Add an object", "Turn into a skeleton", "Turn into a pose figure")
)

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
EDIT_PIXELS = 2048 * 2048
EDIT_SIZES = SIZES
SIZE = ParamSpec("size", "choice", "1024x1024", choices=tuple(Choice(f"{w}x{h}", label) for label, w, h in SIZES))
EDIT_SIZE = ParamSpec(
    "size",
    "choice",
    "match",
    match_first_reference_dimensions=True,
    choices=(
        *(Choice(f"{w}x{h}", label) for label, w, h in EDIT_SIZES),
        Choice("match", "Match first reference dimensions (256 to 4096 per side, up to 4 MP, 4:1)"),
    ),
)
# The checkpoint is distilled to six steps and the engine has no other schedule.
STEP_COUNT = 6
STEPS = ParamSpec("steps", "number", STEP_COUNT, minimum=STEP_COUNT, maximum=STEP_COUNT, integer=True, step=1)
# The engine takes 16. Do not advertise more than the measurement reached.
MAX_REFERENCES = 4

# M5 Pro 64 GiB, int8, Studio API, 2026-11-16. One request per case, six steps.
# The edit uses one 512 x 512 reference; the four-reference run repeats that image.
#                         1024 x 576  1024 x 1024  2048 x 2048  4 refs at 1024
# Generate                  17.13 s       17.13 s       48.37 s       --
# Edit                      36.33 s       39.39 s       81.69 s    136.17 s
# Linear fits give a rough starting estimate. Reference size also affects edit cost.
GENERATE_ESTIMATE = Estimate(step_cost=1.521, exponent=1.0, overhead=9.79, overhead_per_image=True)
EDIT_ESTIMATE = Estimate(
    step_cost=2.15,
    exponent=1.0,
    overhead=27.39,
    overhead_per_image=True,
    per_reference=2.347,
    per_reference_ratio=0.165,
)


def minimax_h3_image_capabilities() -> Capabilities:
    return Capabilities(
        backend_id="minimax_h3_image",
        name="MiniMax H3-Image",
        badge="int8",
        max_batch=4,
        description="Six-step image generation up to 4 MP, and edits with multiple references.",
        # The engine takes its request as request.json and its references as PNG files, and
        # its VAE stage writes the result as a file. A private run keeps no plaintext on disk.
        private_operations=False,
        modes=(
            ModeSpec(
                "generate",
                "Generate",
                (SIZE, STEPS),
                prompt_hint="Describe the complete scene. Put the words of a sign or label in quotes.",
                estimate=GENERATE_ESTIMATE,
                looks=LOOKS,
                templates=TEMPLATES,
            ),
            ModeSpec(
                "edit",
                "Edit",
                (EDIT_SIZE, STEPS),
                min_references=1,
                max_references=MAX_REFERENCES,
                estimate=EDIT_ESTIMATE,
                prompt_hint="Say what to change. Name a reference as <Picture 1>, <Picture 2>, in the order you added them.",
                looks=EDIT_LOOKS,
                templates=EDIT_TEMPLATES,
            ),
        ),
    )
