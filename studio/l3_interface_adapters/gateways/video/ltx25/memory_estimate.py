"""Calibrated memory estimate for ltx25. No engine is loaded."""

from collections.abc import Mapping

from studio.l1_entities.video_estimate import tokens
from studio.l3_interface_adapters.gateways.memory.inputs import (
    _positive_integer,
)

GIB = 1024**3

# The 384 square, 25 frame LTX run used 25 GiB of system headroom. A 1920 by
# 1088, 97 frame run stayed within 64 GiB. Keep 10 GiB for host overhead there.
LTX_SMALL_CLIP_PEAK_GIB = 25.0
LTX_LARGE_CLIP_CEILING_GIB = 54.0
LTX_SMALL_TOKENS = tokens(384, 384, 25)
LTX_LARGE_TOKENS = tokens(1920, 1088, 97)


def estimate_peak_gib(payload: Mapping[str, object]) -> float | None:
    mode = str(payload.get("mode") or "generate")
    if mode != "generate":
        return None
    if payload.get("audio") or payload.get("has_audio") or payload.get("loras") or payload.get("reference_count", 0):
        return None
    if payload.get("references") or payload.get("fast_mode"):
        return None
    if payload.get("enhance", True) is not True:
        return None
    width = _positive_integer(payload.get("width", 384))
    height = _positive_integer(payload.get("height", 384))
    frames = _positive_integer(payload.get("num_frames", 25))
    if width is None or height is None or frames is None:
        return None
    if max(width, height) > 1920 or width * height > 1920 * 1088 or frames > 97:
        return None
    token_count = tokens(width, height, frames)
    if token_count > LTX_LARGE_TOKENS:
        return None
    fraction = max(0.0, token_count - LTX_SMALL_TOKENS) / (LTX_LARGE_TOKENS - LTX_SMALL_TOKENS)
    return LTX_SMALL_CLIP_PEAK_GIB + (LTX_LARGE_CLIP_CEILING_GIB - LTX_SMALL_CLIP_PEAK_GIB) * fraction
