"""Calibrated memory estimate for drama3. No engine is loaded."""

from collections.abc import Mapping

GIB = 1024**3

# Calibrated only on the office M5 Pro, macOS, 64 GiB, with the pinned 8-bit
# MLX checkpoint. Completed scripts of 44, 483, 979 and 2,008 characters
# showed 41.6 to 44.8 GiB less available memory in coarse pressure samples.
# Keep 2.2 GiB above that largest drop. Re-measure after any setup change.
#
# Measured again on 2026-11-12, one seed per case, through the studio's own API:
#
#   case                      drop GiB   seconds
#   clone, 5 s reference       40.96       4.1
#   clone, 15 s reference      42.24       5.1
#   generate, 50 characters    41.60      25.2
#   generate, 700 characters   41.60      29.2
#
# The largest new drop, 42.24 GiB, stays below the 44.8 the constant already
# covers, so 47.0 remains the peak.
DRAMA_CALIBRATED_PEAK_GIB = 47.0
DRAMA_TEXT_GIB_PER_CHARACTER = 0.00015


def estimate_peak_gib(payload: Mapping[str, object]) -> float | None:
    mode = str(payload.get("mode") or "generate")
    if mode != "generate" or payload.get("reference"):
        return None
    text = payload.get("text", payload.get("prompt", ""))
    if not isinstance(text, str):
        return None
    return DRAMA_CALIBRATED_PEAK_GIB + len(text) * DRAMA_TEXT_GIB_PER_CHARACTER
