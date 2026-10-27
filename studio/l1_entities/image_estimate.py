"""What an image request costs, before it runs.

The page writes this figure under its run button, from the mode's `Estimate`. This is the
same formula, so a program that plans a queue gets the figure that the page shows. It reads
the constants only: the rate that a page learns from its own runs stays in that page, so
the answer is the first guess of a fresh tab.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass

from studio.l1_entities.capabilities import Estimate, ModeSpec
from studio.l1_entities.image_job import OptionValue

# The side that the page takes when the shape comes from a reference that it cannot see, or
# from no reference at all: one megapixel.
MATCH_SIDE = 1024
EXCLUDES = ("weight download", "model load", "queue wait")


@dataclass(frozen=True)
class ImageEstimate:
    """The seconds that a request costs.

    `basis` is "constants" when the mode declares an `Estimate`, and "unavailable" when it
    does not, or when it has no step count. The seconds are then None. `width` and `height`
    are the shape that the figure reads; an engine rounds them to its own grid. `steps` and
    `reference_count` are what one image samples and carries. `setup_seconds` is paid once
    for the request, and `per_item_seconds` once for each image. `excludes` names the time
    that the figure does not hold.
    """

    basis: str
    steps: int
    width: int
    height: int
    reference_count: int
    per_item_seconds: float | None = None
    setup_seconds: float | None = None
    total_seconds: float | None = None
    excludes: tuple[str, ...] = EXCLUDES


def estimate_image(
    mode: ModeSpec,
    options: Mapping[str, OptionValue],
    reference_sizes: tuple[tuple[int, int], ...],
    count: int,
    *,
    each: bool = False,
    mask: bool = False,
) -> ImageEstimate:
    """The page's estimate for `count` images of `mode` with these parsed `options`.

    `reference_sizes` are the (width, height) of each reference in the order that a run sends
    them, with the region mask last when `mask` is set. With `each`, every image carries one
    of them. The steps follow form.js `estimate`, and the cost of one step follows its
    `stepSeconds`, operation for operation, so the two give the same number.
    """
    pictures = reference_sizes[:-1] if mask else reference_sizes
    carried = 1 if each else len(reference_sizes)
    model = mode.reference_estimate if pictures and mode.reference_estimate else mode.estimate
    pixels, width, height = _shape(options, pictures, model)
    steps = int(options.get("steps", 0))
    if model is None or "steps" not in options:
        return ImageEstimate("unavailable", steps, width, height, carried)
    if model.strength_scales_steps and pictures:
        # mflux skips the start of the schedule for a starting image.
        steps -= max(1, math.floor(steps * float(options.get("strength", 0))))
    # The constant holds the passes that it was measured with, so it is scaled to the passes
    # that these options ask for.
    passes = (2 if _two_pass(options) else 1) / (2 if model.two_pass else 1)
    growth = 1 + model.per_reference * max(0, carried - 1) if model.per_reference else 1
    step_seconds = model.step_cost * passes * growth * math.pow(pixels / 1e6, model.exponent)
    per_item = steps * step_seconds + (model.overhead if model.overhead_per_image else 0)
    setup = 0.0 if model.overhead_per_image else model.overhead
    return ImageEstimate(
        "constants",
        steps,
        width,
        height,
        carried,
        round(per_item, 1),
        round(setup, 1),
        round(count * per_item + setup, 1),
    )


def _shape(
    options: Mapping[str, OptionValue], pictures: tuple[tuple[int, int], ...], model: Estimate | None
) -> tuple[int, int, int]:
    """The pixel count that the cost reads, and the width and height of that area.

    A mode with a resolution setting takes its pixels from it, and its shape from the last
    reference, as the edit engines do. "match" keeps that reference's own pixels, up to the
    estimate's `match_cap`. A size setting names both sides.
    """
    reference = pictures[-1] if pictures else None
    ratio = reference[0] / reference[1] if reference else 1.0
    if "resolution" in options:
        chosen = str(options["resolution"])
        if chosen != "match":
            side = int(chosen)
        elif reference:
            side = _rounded(math.sqrt(reference[0] * reference[1]))
            side = min(side, model.match_cap) if model and model.match_cap else side
        else:
            side = MATCH_SIDE
        return side * side, *_sides(side * side, ratio)
    width, _, height = str(options.get("size", "")).partition("x")
    if width.isdigit() and height.isdigit():
        return int(width) * int(height), int(width), int(height)
    return MATCH_SIDE * MATCH_SIDE, *_sides(MATCH_SIDE * MATCH_SIDE, ratio)


def _two_pass(options: Mapping[str, OptionValue]) -> bool:
    """Guidance above 1 runs a second pass each step. A mode with a negative prompt runs it
    only while a negative is set, so a blank one takes the time of guidance 1."""
    scale = "cfg" if "cfg" in options else "guidance" if "guidance" in options else ""
    if not scale or float(options[scale]) <= 1:
        return False
    return "negative" not in options or bool(options["negative"])


def _sides(pixels: int, ratio: float) -> tuple[int, int]:
    return _rounded(math.sqrt(pixels * ratio)), _rounded(math.sqrt(pixels / ratio))


def _rounded(number: float) -> int:
    """A half rounds up, as the page's Math.round does. Python's round() takes it to even."""
    return math.floor(number + 0.5)
