"""Calibrated memory estimate for qwen21_turbo. No engine is loaded.

Measured on the office M5 Pro, 64 GiB, bf16, one seed per case, 2026-11-12.
The peak is the process footprint from `footprint -p`, sampled once a second.

Generate is a step, not a curve: 29 to 30 GiB up to 768, then 49 to 51 GiB from
1024. Edit is linear in output megapixels and reference count:
`48.22 + 0.65 * MP + 1.92 * refs`, plus the 1.2 GiB largest residual. The 1344
edit did not finish: Metal ran out of memory at a 52.48 GiB drop, so every edit
above 1.2 MP takes a 56 GiB floor. Input size does not move the peak: a 512 and a
4032 by 3024 reference measured 51 and 52 GiB.
"""

from collections.abc import Mapping

from studio.l3_interface_adapters.gateways.memory.inputs import (
    _edit_megapixels,
    _has_loras,
    _image_size,
    _reference_sizes,
)

GIB = 1024**3
# The weight bytes that stay resident while the model is loaded, for a boundary policy.
QWEN_TURBO_WEIGHTS_GIB = 30_000_000_000 / GIB
QWEN_TURBO_CALIBRATED_QUANTIZE = None
QWEN_TURBO_GENERATE_SMALL_GIB = 31.0
QWEN_TURBO_GENERATE_LARGE_GIB = 52.0
QWEN_TURBO_EDIT_BASE_GIB = 48.22
QWEN_TURBO_EDIT_PER_MP_GIB = 0.65
QWEN_TURBO_EDIT_PER_REFERENCE_GIB = 1.92
QWEN_TURBO_EDIT_MARGIN_GIB = 1.20
QWEN_TURBO_EDIT_LARGE_MP = 1.2
QWEN_TURBO_EDIT_MATCH_CAP = 1344
QWEN_TURBO_EDIT_LARGE_FLOOR_GIB = 56.0
QWEN_TURBO_MAX_REFERENCES = 10


def estimate_peak_gib(payload: Mapping[str, object], *, quantize: int | None = None) -> float | None:
    if quantize != QWEN_TURBO_CALIBRATED_QUANTIZE or _has_loras(payload.get("loras")):
        return None
    mode = str(payload.get("mode") or "generate")
    references = _reference_sizes(payload.get("references"), payload.get("reference_sizes"))
    if references is None:
        return None
    if mode == "generate":
        return _generate(payload, references)
    if mode == "edit":
        return _edit(payload, references)
    return None


def _generate(payload: Mapping[str, object], references: tuple[tuple[int, int], ...]) -> float | None:
    if references or payload.get("mask") or payload.get("each_reference"):
        return None
    width, height = _image_size(payload.get("size", "512x512"))
    if width is None or height is None:
        return None
    megapixels = width * height / 1_000_000
    if megapixels > 1328 * 1328 / 1_000_000:
        return None
    return QWEN_TURBO_GENERATE_LARGE_GIB if megapixels >= 1.0 else QWEN_TURBO_GENERATE_SMALL_GIB


def _edit(payload: Mapping[str, object], references: tuple[tuple[int, int], ...]) -> float | None:
    if not references or len(references) > QWEN_TURBO_MAX_REFERENCES:
        return None
    if payload.get("mask") and len(references) < 2:
        return None
    # One image per reference edits each on its own, so only one is in memory.
    count = 1 if payload.get("each_reference") else len(references)
    megapixels = _edit_megapixels(payload.get("resolution"), references, QWEN_TURBO_EDIT_MATCH_CAP)
    if megapixels is None:
        return None
    peak = (
        QWEN_TURBO_EDIT_BASE_GIB
        + QWEN_TURBO_EDIT_PER_MP_GIB * megapixels
        + QWEN_TURBO_EDIT_PER_REFERENCE_GIB * count
        + QWEN_TURBO_EDIT_MARGIN_GIB
    )
    if megapixels > QWEN_TURBO_EDIT_LARGE_MP:
        peak = max(peak, QWEN_TURBO_EDIT_LARGE_FLOOR_GIB)
    return round(peak, 2)
