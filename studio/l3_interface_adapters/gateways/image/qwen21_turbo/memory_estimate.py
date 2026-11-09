"""Calibrated memory estimate for qwen21_turbo. No engine is loaded."""

from collections.abc import Mapping

from studio.l3_interface_adapters.gateways.memory.inputs import (
    _has_loras,
    _image_size,
    _reference_sizes,
)

GIB = 1024**3

# Office M5 Pro, BF16 Qwen Turbo: 53.1 GiB at 1328 square.
# Edits have no calibrated peak; admission leaves them to the engine's memory policy.
QWEN_TURBO_WEIGHTS_GIB = 30_000_000_000 / GIB
QWEN_TURBO_GENERATE_PEAK_GIB = 53.1
QWEN_TURBO_CALIBRATED_QUANTIZE = None


def estimate_peak_gib(payload: Mapping[str, object], *, quantize: int | None = None) -> float | None:
    mode = str(payload.get("mode") or "generate")
    if quantize != QWEN_TURBO_CALIBRATED_QUANTIZE:
        return None
    if _has_loras(payload.get("loras")):
        return None
    references = _reference_sizes(payload.get("references"), payload.get("reference_sizes"))
    if references is None:
        return None
    if mode != "generate":
        return None
    if references or payload.get("mask") or payload.get("each_reference"):
        return None
    width, height = _image_size(payload.get("size", "512x512"))
    if width is None or height is None:
        return None
    megapixels = width * height / 1_000_000
    if megapixels > 1328 * 1328 / 1_000_000:
        return None
    if megapixels >= 1.0:
        return QWEN_TURBO_GENERATE_PEAK_GIB
    workspace = QWEN_TURBO_GENERATE_PEAK_GIB - QWEN_TURBO_WEIGHTS_GIB
    return QWEN_TURBO_WEIGHTS_GIB + workspace * megapixels / (1328 * 1328 / 1_000_000)
