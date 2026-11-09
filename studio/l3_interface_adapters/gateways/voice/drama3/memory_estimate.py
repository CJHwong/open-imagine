"""Calibrated memory estimate for drama3. No engine is loaded."""

from collections.abc import Mapping

GIB = 1024**3

# Calibrated only on the office M5 Pro, macOS, 64 GiB, with the pinned 8-bit
# MLX checkpoint. Completed scripts of 44, 483, 979 and 2,008 characters
# showed 41.6 to 44.8 GiB less available memory in coarse pressure samples.
# Keep 2.2 GiB above that largest drop. Re-measure after any setup change.
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
