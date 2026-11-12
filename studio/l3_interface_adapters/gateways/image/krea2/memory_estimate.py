"""Calibrated memory estimate for krea2. No engine is loaded."""

from collections.abc import Mapping

from studio.l3_interface_adapters.gateways.memory.inputs import (
    _has_loras,
    _image_size,
    _reference_sizes,
)

GIB = 1024**3

# Office M5 Pro, the int8 Krea 2 Turbo weights, through Krea2Model with no other
# GPU job. The largest drop in free memory from a baseline before the load:
# 29.4 to 33.9 GiB at 512 square, text or one reference; 40.3 to 46.7 GiB from
# 768 square to 1024 square, for text, one reference, Match from a 1600 by 900
# photo, a 4032 by 3024 reference and two images in a row. MLX's own peak was
# 28.0 and 35.2 GiB; the rest is the page cache of the 22 GB of weights. 768
# square already reached 44.8 GiB, so every size above 512 square takes the top.
KREA2_SMALL_PEAK_GIB = 34.0
KREA2_SMALL_PIXELS = 512 * 512
KREA2_PEAK_GIB = 47.0
KREA2_MAX_PIXELS = 1024 * 1024
KREA2_DEFAULT_SIZE = "1024x1024"
# The stored int8 weights are 22 GB, as the peak note above records. Idle, the model
# holds those weights and little else, so this is what a boundary policy retains.
KREA2_WEIGHTS_GIB = 22.0


def estimate_peak_gib(payload: Mapping[str, object]) -> float | None:
    """Text to image or one starting image, up to the 1 MP the measurement reached."""
    mode = str(payload.get("mode") or "generate")
    if mode != "generate" or _has_loras(payload.get("loras")):
        return None
    if payload.get("mask") or payload.get("each_reference"):
        return None
    references = _reference_sizes(payload.get("references"), payload.get("reference_sizes"))
    if references is None or len(references) > 1:
        return None
    # Match sizes the output from the reference at about 1 MP; _image_size reads it as 1024 square.
    width, height = _image_size(payload.get("size", KREA2_DEFAULT_SIZE))
    if width is None or height is None or width * height > KREA2_MAX_PIXELS:
        return None
    return KREA2_SMALL_PEAK_GIB if width * height <= KREA2_SMALL_PIXELS else KREA2_PEAK_GIB
