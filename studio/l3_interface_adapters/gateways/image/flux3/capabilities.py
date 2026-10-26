"""Distilled FLUX3 Image Klein: its native controls, without untested prompt aids."""

from dataclasses import replace

from studio.l1_entities.capabilities import Capabilities, Choice, ModeSpec, ParamSpec

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


def flux3_capabilities(badge: str) -> Capabilities:
    return Capabilities(
        backend_id="flux3",
        name="FLUX3 Image Klein",
        badge=badge,
        max_batch=4,
        description="Optional distilled model. Generate and compose with up to 2 references; describe the full scene.",
        modes=(
            ModeSpec(
                "generate",
                "Generate",
                (SIZE, STEPS),
                max_references=MAX_REFERENCES,
                prompt_hint="Describe the complete scene: subject, framing, background, light and style.",
            ),
            ModeSpec(
                "edit",
                "Edit",
                (replace(SIZE, default="match"), STEPS),
                min_references=1,
                max_references=MAX_REFERENCES,
                prompt_hint="Describe the complete target image with your changes included.",
            ),
        ),
    )
