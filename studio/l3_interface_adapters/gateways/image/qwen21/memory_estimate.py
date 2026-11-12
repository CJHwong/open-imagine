"""Calibrated memory estimate for qwen21. No engine is loaded.

Measured on the office M5 Pro, 64 GiB, bf16, one seed per case, 2026-11-12.
The peak is the process footprint from `footprint -p`, sampled once a second.

Generate is a step: 43 to 50 GiB up to 768, then 54 to 55 GiB from 1024. Edit is
linear in output megapixels and reference count:
`57.03 + 6.06 * MP + 1.68 * refs`, plus the 2.74 GiB largest residual. A 1344
edit measured 71 GiB and completed; the machine compressed. Input size does not
move the peak: a 512 and a 4032 by 3024 reference measured 61 and 63 GiB.
"""

from collections.abc import Mapping

from studio.l3_interface_adapters.gateways.memory.inputs import (
    _edit_megapixels,
    _has_loras,
    _image_size,
    _reference_sizes,
)

QWEN21_CALIBRATED_QUANTIZE = None
QWEN21_GENERATE_SMALL_GIB = 51.0
QWEN21_GENERATE_LARGE_GIB = 56.0
QWEN21_EDIT_BASE_GIB = 57.03
QWEN21_EDIT_PER_MP_GIB = 6.06
QWEN21_EDIT_PER_REFERENCE_GIB = 1.68
QWEN21_EDIT_MARGIN_GIB = 2.74
QWEN21_MAX_REFERENCES = 10
QWEN21_EDIT_MATCH_CAP = 1344


def estimate_peak_gib(payload: Mapping[str, object], *, quantize: int | None = None) -> float | None:
    if quantize != QWEN21_CALIBRATED_QUANTIZE or _has_loras(payload.get("loras")):
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
    return QWEN21_GENERATE_LARGE_GIB if megapixels >= 1.0 else QWEN21_GENERATE_SMALL_GIB


def _edit(payload: Mapping[str, object], references: tuple[tuple[int, int], ...]) -> float | None:
    if not references or len(references) > QWEN21_MAX_REFERENCES:
        return None
    if payload.get("mask") and len(references) < 2:
        return None
    count = 1 if payload.get("each_reference") else len(references)
    megapixels = _edit_megapixels(payload.get("resolution"), references, QWEN21_EDIT_MATCH_CAP)
    if megapixels is None:
        return None
    return round(
        QWEN21_EDIT_BASE_GIB
        + QWEN21_EDIT_PER_MP_GIB * megapixels
        + QWEN21_EDIT_PER_REFERENCE_GIB * count
        + QWEN21_EDIT_MARGIN_GIB,
        2,
    )
