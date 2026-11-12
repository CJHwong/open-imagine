"""Calibrated memory estimate for yue2. No engine is loaded."""

from collections.abc import Mapping

GIB = 1024**3

# YuE2's active weight files total 9.7 GB. A short 8-step song used 4.5 GiB
# of system headroom. The weight floor and input terms below are conservative.
#
# Measured again on 2026-11-12, office M5 Pro, 64 GiB, one seed per case:
#
#   case             drop GiB   footprint GiB   seconds
#   generate short      3.84       36.02         160.2
#   generate long       3.84       36.02         237.9
#   generate inst.      4.48       36.02         283.2
#   plan short          3.20       35.40          10.1
#
# The drop is small because the server already held the weights. The 10 GiB
# floor is the 9.7 GB of weight files, which a cold run must load.
YUE2_WEIGHT_FLOOR_GIB = 10.0
YUE2_TRANSCRIPTION_LIMIT_GIB = 16.0


def estimate_peak_gib(payload: Mapping[str, object]) -> float | None:
    mode = str(payload.get("mode") or "generate")
    if mode == "transcribe":
        return YUE2_TRANSCRIPTION_LIMIT_GIB
    if mode not in ("generate", "plan", "cover"):
        return None
    lyrics = payload.get("lyrics", "")
    style = payload.get("style", "")
    score = payload.get("abc", "")
    if not isinstance(lyrics, str) or not isinstance(style, str) or not isinstance(score, str):
        return None
    if len(lyrics) > 20_000 or len(style) > 4_000 or len(score) > 100_000:
        return None
    sampling = payload.get("sampling") or {}
    if not isinstance(sampling, Mapping):
        return None
    default_tokens = 4096 if mode == "plan" else 9000
    max_tokens = sampling.get("max_tokens", default_tokens)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 16_000:
        return None
    generation_peak = (
        YUE2_WEIGHT_FLOOR_GIB + len(lyrics) * 0.00025 + len(style) * 0.0001 + len(score) * 0.00005 + max_tokens * 0.0001
    )
    if payload.get("instrumental") is True:
        generation_peak += 2.0
    if mode == "cover":
        return max(YUE2_TRANSCRIPTION_LIMIT_GIB, generation_peak)
    return generation_peak
