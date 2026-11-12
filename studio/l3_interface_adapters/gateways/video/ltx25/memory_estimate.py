"""Calibrated memory estimate for ltx25. No engine is loaded."""

from collections.abc import Mapping

from studio.l1_entities.video_estimate import tokens
from studio.l3_interface_adapters.gateways.memory.inputs import (
    _positive_integer,
)

GIB = 1024**3

# The 384 square, 25 frame LTX run used 25 GiB of system headroom. A 1920 by
# 1088, 97 frame run stayed within 64 GiB. Keep 10 GiB for host overhead there.
#
# Measured again on 2026-11-12, office M5 Pro, 64 GiB, one seed per case, through
# the studio's own API, with free memory and the process tree sampled once a
# second. Drop is the fall in free memory; footprint is the whole server tree.
#
#   case                              drop GiB   footprint GiB   seconds
#   384x384x25                         21.33       49.04          26.2
#   768x768x97                         12.80       51.04         135.1
#   1280x704x97                        14.08       53.04         269.2
#   1920x1088x97                       14.08       59.04         750.9
#   frames 25 / 49 / 121 at 768        15.36 / 13.44 / 15.36   59.4 / 88.7 / 200.6
#   keyframes 1 / 2 / 4 / 8 at 768     16.64 / 16.64 / 18.35 / 18.56
#                                      162.3 / 171.4 / 199.7 / 245.9
#   fast 768x768x121                   20.48       51.04         149.1
#   no-enhance 768x768x97              21.76       51.04         160.3
#   audio 768x768x97                   24.96       58.04         849.1
#
# The drop of the large case is small because its weights were already in the
# server. The footprint is the figure that approaches the machine's limit, and
# the largest was 59.04 GiB. The 54 GiB ceiling stays: a 64 GiB machine then keeps
# under 10 GiB for the host, which is what the ceiling already reserves.
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
