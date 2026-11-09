"""Calibrated MiniMax H3 peaks; inference is supplied by the installed plugin."""

import json
from collections.abc import Mapping

from studio.l3_interface_adapters.gateways.memory.inputs import _positive_integer

# Staged Q8 MiniMax H3. Two page runs of 175 frames were sampled once a second. From an idle
# 87%, macOS free memory fell to 33% at 1024 by 576 (34.6 GiB) and to 11% at 1280 by 704
# (48.6 GiB). The smaller run was sampled only in its last denoise steps, but the larger run
# held its low through every step. Keep 1 GiB above each drop, because memory_pressure
# reports whole percents. The text encoder alone used about 31.4 GiB, so a smaller clip
# keeps the smaller run's figure. The runs did not record their stills or track.
H3_SMALL_CLIP_PEAK_GIB = 35.6
H3_LARGE_CLIP_PEAK_GIB = 49.6
H3_MEASURED_FRAMES = 175
# One LoRA on H3: a run of 1024 by 576 and 175 frames through the plugin's own gateway, sampled
# about once a second from start to end. The LoRA was rank 16 on mlp.fc1 and mlp.fc2, 86 MB, at
# strength 0.7. From an idle 88%, macOS free memory fell to 30% in the first denoise step and
# stayed at 31 to 33% after it. That is 37.1 GiB, so keep 38.1 GiB: 2.5 GiB over the run without
# a LoRA. The worker footprint rose only 0.7 GiB over that run, and at 512 by 288 the denoise peak
# rose 0.14 GiB. Much of the 2.5 GiB may be the first step, which the earlier sampling missed, but
# count all of it, and let it grow with the rows. Two LoRAs at once were not measured.
H3_LORA_GIB = 2.5
H3_MEASURED_SIDE = 1280


def _lora_count(raw: object) -> int | None:
    """The number of LoRA picks, or None for a value that this cannot read."""
    if raw in (None, "", [], ()):
        return 0
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    return len(raw) if isinstance(raw, list) else None


def estimate_peak_gib(payload: Mapping[str, object]) -> float | None:
    mode = payload.get("mode") or "generate"
    loras = _lora_count(payload.get("loras"))
    if mode != "generate" or loras is None or loras > 1:
        return None
    references = payload.get("references") or []
    if not isinstance(references, list):
        return None
    width = _positive_integer(payload.get("width"))
    height = _positive_integer(payload.get("height"))
    frames = _positive_integer(payload.get("num_frames"))
    if width is None or height is None or frames is None:
        return None
    # The audio rows grow with the frame count and are not counted below, so a longer clip
    # is unmeasured at any size.
    if max(width, height) > H3_MEASURED_SIDE or frames > H3_MEASURED_FRAMES or (frames - 5) % 17:
        return None
    rows = _h3_rows(width, height, frames, len(references))
    if rows > H3_LARGE_ROWS:
        return None
    # A straight line between the two runs stays above any need that grows linearly or
    # faster with the rows.
    fraction = max(0.0, rows - H3_SMALL_ROWS) / (H3_LARGE_ROWS - H3_SMALL_ROWS)
    peak = H3_SMALL_CLIP_PEAK_GIB + (H3_LARGE_CLIP_PEAK_GIB - H3_SMALL_CLIP_PEAK_GIB) * fraction
    # A smaller clip keeps the measured LoRA figure, as it keeps the run's own.
    return peak + loras * H3_LORA_GIB * max(1.0, rows / H3_SMALL_ROWS)


def _h3_rows(width: int, height: int, frames: int, stills: int) -> int:
    """The packed video rows of one H3 run. 17n + 5 frames make 5n + 2 latent frames of
    (W / 32) x (H / 32) rows each. A still adds one latent frame of conditioning rows. A
    track fills the target audio rows, so it adds none."""
    latent_frames = (frames - 5) // 17 * 5 + 2
    return (latent_frames + stills) * -(-width // 32) * -(-height // 32)


H3_SMALL_ROWS = _h3_rows(1024, 576, H3_MEASURED_FRAMES, 0)
H3_LARGE_ROWS = _h3_rows(1280, 704, H3_MEASURED_FRAMES, 0)
