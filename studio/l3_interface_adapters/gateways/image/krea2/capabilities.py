"""What the Krea 2 Turbo backend offers the page, and the limits the core checks."""

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec

MATCH = "match"
MAX_BATCH = 4
# The distilled schedule from the model card. Turbo is timestep-distilled for 8 steps.
SCHEDULE_STEPS = 8

# Three tiers per shape, on the 16-pixel grid. mflux calibrates the sigma shift for
# up to about 1280 x 1280, so the largest tier stays near 1 MP.
SIZES = (
    ("1024 x 1024", 1024, 1024),
    ("512 x 512", 512, 512),
    ("768 x 768", 768, 768),
    ("768 x 432 (16:9)", 768, 432),
    ("1024 x 576 (16:9)", 1024, 576),
    ("1280 x 720 (16:9)", 1280, 720),
    ("432 x 768 (9:16)", 432, 768),
    ("576 x 1024 (9:16)", 576, 1024),
    ("720 x 1280 (9:16)", 720, 1280),
    ("640 x 480 (4:3)", 640, 480),
    ("896 x 672 (4:3)", 896, 672),
    ("1152 x 864 (4:3)", 1152, 864),
    ("480 x 640 (3:4)", 480, 640),
    ("672 x 896 (3:4)", 672, 896),
    ("864 x 1152 (3:4)", 864, 1152),
)

# Whole runs on an M5 Pro, 64 GB, int8 weights, guidance 1 (one pass), through
# Krea2Model with no other GPU job, on 2026-11-08 and 2026-11-09. Seconds:
#
#   megapixels                        0.26        0.59        1.05
#   text to image, 8 steps       17.5, 20.3  36.1, 39.4  64.5, 74.8 to 83.8
#   one reference, 7 steps       14.3, 32.9        35.2  73.3, 79.1, 86.2
#
# The same run took up to 30% longer on the second day, with more of the
# machine's memory in use. The time outside the steps grows with the size (the
# decode, and a reference's encode), and an Estimate has one constant for it, so
# each line is fitted on the whole run time over every size: text is within 10%
# on average and 19% at worst. The reference line has a steep exponent for the
# same reason. It is within 12% at 1 MP for strength 0.05 to 0.7, but the two
# 512 runs differ by 2.3 times, and the estimate sits between them.
GENERATE_ESTIMATE = Estimate(step_cost=8.6, exponent=1.16, overhead=4, overhead_per_image=True)
GENERATE_REFERENCE_ESTIMATE = Estimate(
    step_cost=9.3, exponent=1.6, overhead=10, overhead_per_image=True, strength_scales_steps=True
)

SIZE = ParamSpec(
    id="size",
    kind="choice",
    default="1024x1024",
    choices=(
        *(Choice(f"{width}x{height}", label) for label, width, height in SIZES),
        Choice(MATCH, "Match reference (about 1 MP)"),
    ),
)
STEPS = ParamSpec(
    id="steps",
    kind="number",
    default=SCHEDULE_STEPS,
    minimum=SCHEDULE_STEPS,
    maximum=SCHEDULE_STEPS,
    integer=True,
    step=1,
)
# mflux's shared Config.init_time_step: the strength is the share of the schedule
# skipped, so higher stays closer to the reference. At 1.0 no step runs and the
# output is the reference after a VAE round trip, so the top is 0.95.
STRENGTH = ParamSpec(id="strength", kind="number", default=0.4, minimum=0.05, maximum=0.95, step=0.05)

# No guidance and no negative prompt. Turbo is distilled to run without CFG at
# guidance 1.0. Any other value makes mflux run two transformer passes per step,
# and below 1 too, which the shared estimate does not count.
GENERATE = ModeSpec(
    id="generate",
    label="Generate",
    params=(SIZE, STEPS, STRENGTH),
    max_references=1,  # Krea2.generate_image takes one image_path for img2img
    prompt_hint="Describe the image. Add a reference to start from it.",
    estimate=GENERATE_ESTIMATE,
    reference_estimate=GENERATE_REFERENCE_ESTIMATE,
)


def krea2_capabilities(badge: str = "int8") -> Capabilities:
    return Capabilities(
        backend_id="krea2",
        name="Krea 2 Turbo",
        badge=badge,
        modes=(GENERATE,),
        max_batch=MAX_BATCH,
        description="Polished images with varied styles for creative exploration.",
    )
