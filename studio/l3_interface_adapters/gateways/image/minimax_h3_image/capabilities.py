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
# An edit at 1024 x 1024 came out posterized and over-sharpened; the same edit at 2048 x 2048
# was clean (M5 Pro 64 GiB, int8, one reference, 2026-11-11). The reference pipeline also holds
# an edit at 4 MP or more, so Edit offers only the sizes of about 4 MP.
EDIT_PIXELS = 2048 * 2048
EDIT_SIZES = tuple(size for size in SIZES if size[1] * size[2] >= 3_600_000)
SIZE = ParamSpec("size", "choice", "1024x1024", choices=tuple(Choice(f"{w}x{h}", label) for label, w, h in SIZES))
EDIT_SIZE = ParamSpec(
    "size",
    "choice",
    "match",
    choices=(
        *(Choice(f"{w}x{h}", label) for label, w, h in EDIT_SIZES),
        Choice("match", "Match first reference (about 4 MP)"),
    ),
)
# The checkpoint is distilled to six steps and the engine has no other schedule.
STEP_COUNT = 6
STEPS = ParamSpec("steps", "number", STEP_COUNT, minimum=STEP_COUNT, maximum=STEP_COUNT, integer=True, step=1)
# The engine takes 16. Do not advertise more than the measurement reached.
MAX_REFERENCES = 4

# Measured on 2026-11-11 through this gateway and the studio's process runner, M5 Pro 64 GiB,
# the int8 weights, one run at a time with no other GPU job. Seconds for one image, and the
# seconds for each step after the first:
#
#   Generate   1024 x 576    16.8 s   0.9 per step
#              1024 x 1024   20.9 and 19.8 s   1.8 per step
#              1536 x 864    26.4 s   3.0 per step
#              2560 x 1440   49.9 s   6.7 per step
#              2048 x 2048   55.7 s   7.7 per step
#   Edit at 2048 x 2048, by reference
#              one of 1024 x 1024     94.3 s   13.4 per step
#              one of 2048 x 2048    142.9 s   20.7 per step
#              two of 2048 x 2048    252.3 s   37.1 per step
#              four of 2048 x 2048   556.4 s   84.6 per step
#   Edit, other shapes
#              Match from 1600 x 900, 2720 x 1536   130.0 s   18.9 per step
#              2560 x 1440, four of 2048 x 2048     548.4 s   83.1 per step
#   Edit with Match, from one long reference of about 4 MP
#              2896 x 1448 (2:1), 2912 x 1440       164.8 s   23.9 per step
#              6000 x 2000 (3:1), which the gateway sends at 3547 x 1182,
#              3552 x 1184                          184.4 s
#              4096 x 1024 (4:1), 4096 x 1024       208.4 s   30.3 per step
#
# A step grows with the pixel count, so the exponent is 1. The rest of a run is about ten
# seconds: four children start, and the transformer loads before the first step.
GENERATE_ESTIMATE = Estimate(step_cost=1.85, exponent=1.0, overhead=10.0, overhead_per_image=True)
# An edit attends to every reference, and the engine reads one at up to 2048 pixels a side, so
# the pixels of the references set the cost more than the output does. Past 8192 rows, which
# one 2048 x 2048 reference reaches, the engine stops holding the transformer and streams it.
# The constants take a large reference, as a phone photo is. The page reads Match as 1 MP and
# every Edit size is about 4 MP, so the exponent is 0 and the step cost is the cost at 4 MP.
#
# The text encoder reads each reference a second time with its short side at 1024 pixels, so a
# reference of 3:1 gives it three times the rows of a square one, at any pixel count. The three
# long runs above each sit near one more 0.165 of the step cost for each unit of the ratio past
# 1:1: this estimate says 165, 185 and 206 s for them. The gateway refuses a reference past 4:1.
EDIT_ESTIMATE = Estimate(
    step_cost=20.7,
    exponent=0.0,
    overhead=20.0,
    overhead_per_image=True,
    per_reference=0.95,
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
