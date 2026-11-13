"""Distilled FLUX3 Image Klein: its native controls, without untested prompt aids."""

from dataclasses import replace

from studio.l1_entities.capabilities import Capabilities, Choice, Estimate, ModeSpec, ParamSpec

SIZES = (
    ("512 x 512", 512, 512),
    ("768 x 768", 768, 768),
    ("1024 x 1024", 1024, 1024),
    ("768 x 432 (16:9)", 768, 432),
    ("1024 x 576 (16:9)", 1024, 576),
    ("1280 x 720 (16:9)", 1280, 720),
    ("432 x 768 (9:16)", 432, 768),
    ("576 x 1024 (9:16)", 576, 1024),
    ("768 x 1024 (3:4)", 768, 1024),
    ("1024 x 768 (4:3)", 1024, 768),
)
SIZE = ParamSpec(
    "size",
    "choice",
    "1024x1024",
    choices=(
        *(Choice(f"{w}x{h}", label) for label, w, h in SIZES),
        Choice("match", "Match first reference (up to 1 MP)"),
    ),
)
STEPS = ParamSpec("steps", "number", 16, minimum=1, maximum=50, integer=True, step=1)
# Two-reference composition was exercised through Studio. Do not advertise the
# upstream ten-reference maximum until its memory cost is measured locally.
MAX_REFERENCES = 2

# Whole runs on an M5 Pro, 64 GB, eight-bit weights, 16 steps, through the studio's own
# route on 2026-11-13 with no other GPU job. Seconds:
#
#   megapixels                        0.26    0.59    1.05
#   text to image                     12.6    24.9    54.3
#   one reference                     28.8    46.1    77.4
#   two references                    38.0    53.0    85.1
#
# The load is not in these figures. Both reference rows share one curve: a reference
# costs 0.19 more of the step time for the second. The fit reproduces the text row and
# is within 4% of the reference rows above 0.26 MP, and within 12% at 0.26 MP, where a
# fixed encode cost dominates.
#
# The size choice matches a reference up to 1 MP, so the cap is the side of 1024 square.
MATCH_CAP = 1024
GENERATE_ESTIMATE = Estimate(step_cost=2.6, exponent=1.82, overhead=9, overhead_per_image=True, match_cap=MATCH_CAP)
REFERENCE_ESTIMATE = Estimate(
    step_cost=3.05,
    exponent=1.34,
    overhead=24,
    overhead_per_image=True,
    match_cap=MATCH_CAP,
    per_reference=0.19,
)


def flux3_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="flux3",
        name="FLUX3 Image Klein",
        badge=badge,
        max_batch=4,
        description="Fast instruction edits and image composition from multiple references.",
        modes=(
            ModeSpec(
                "generate",
                "Generate",
                (SIZE, STEPS),
                max_references=MAX_REFERENCES,
                prompt_hint="Describe the complete scene: subject, framing, background, light and style.",
                estimate=GENERATE_ESTIMATE,
                reference_estimate=REFERENCE_ESTIMATE,
            ),
            ModeSpec(
                "edit",
                "Edit",
                (replace(SIZE, default="match"), STEPS),
                min_references=1,
                max_references=MAX_REFERENCES,
                prompt_hint="Describe the complete target image with your changes included.",
                reference_estimate=REFERENCE_ESTIMATE,
            ),
        ),
    )
