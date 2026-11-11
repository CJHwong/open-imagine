"""Calibrated memory estimate for minimax_h3_image. No engine is loaded."""

from collections.abc import Mapping

from studio.l3_interface_adapters.gateways.image.minimax_h3_image.capabilities import MAX_REFERENCES
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.minimax_h3_image_backend_gateway import (
    MAX_REFERENCE_RATIO,
)
from studio.l3_interface_adapters.gateways.memory.inputs import _has_loras, _image_size, _reference_sizes

# M5 Pro 64 GiB, the int8 weights, through the gateway with no other GPU job, 2026-11-11.
# Twelve runs: text to image from 1024 x 576 to 2048 x 2048, and edits at about 4 MP with one,
# two and four references of up to 2048 x 2048. The largest drop in free memory from a baseline
# before the run was 21.1 GiB, on the first run, which also filled the page cache. MLX's own
# peak was 18.6 to 20.9 GiB while the engine held the transformer. An edit past 8192 rows
# streams the transformer and peaked at 3.7 to 8.8 GiB, so the held case is the top.
H3_IMAGE_PEAK_GIB = 22.0
# Match gives 4096 x 1024 at most, and the largest size on the form has fewer pixels.
H3_IMAGE_MAX_PIXELS = 2048 * 2048


def estimate_peak_gib(payload: Mapping[str, object]) -> float | None:
    """Generate or edit inside what the measurement reached; nothing for a request outside it."""
    mode = str(payload.get("mode") or "generate")
    if mode not in ("generate", "edit") or _has_loras(payload.get("loras")):
        return None
    if payload.get("mask") or payload.get("each_reference"):
        return None
    references = _reference_sizes(payload.get("references"), payload.get("reference_sizes"))
    if references is None or len(references) > MAX_REFERENCES:
        return None
    # The gateway refuses a longer reference, and sends a larger one at 2048 x 2048 pixels at most.
    if any(max(size) > MAX_REFERENCE_RATIO * min(size) for size in references):
        return None
    # Match sizes the output from the reference at about 4 MP; _image_size reads it as 1024 square.
    width, height = _image_size(payload.get("size", "1024x1024"))
    if width is None or height is None or width * height > H3_IMAGE_MAX_PIXELS:
        return None
    return H3_IMAGE_PEAK_GIB
