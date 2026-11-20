"""The LTX-2.5 form on the CUDA engine.

The shapes, frame counts and reference rules are the model's, so they come from the same
shared record the MLX backend uses. What differs is the identity, the precision the weights
actually run at, and the cost of a clip on this machine.
"""

from dataclasses import replace

from studio.l1_entities.video_capabilities import VideoCapabilities, VideoEstimate
from studio.l3_interface_adapters.gateways.video.shared.capabilities import (
    ltx25_mlx_capabilities,
    video_estimate,
)

# The measured cost here, DGX Spark GB10, bf16 weights, the distilled eight-step schedule,
# 97 frames, one operation at a time through the studio API on 2026-11-15. Warm runs, after
# the first case paid the 32.3 s load:
#
#   768 x 448    48.3 s
#   768 x 768    76.3 s
#   768 x 512, one keyframe at frame 0, strength 1.0    55.3 s
#   1280 x 704  121.5 s
#
# The shared record's shape holds the stages and the decode, and the fit here is two
# constants: 0.530 of its figure, plus 14.2 s of fixed cost. The API rounds a clip to the
# nearest 10 s, so it answers 50, 80 and 120 s for the three sizes above, against the
# measured 48.3, 76.3 and 121.5 s. Before that rounding the fit reads 47.4, 77.8 and
# 120.9 s.
#
# That is far from the MLX record it replaces. The shared constants are a fixed 87.0 s plus
# 1.46 of the same figure, which reads 270 s for the 768 x 768 clip that this machine runs
# in 76.3 s and the Mac in 117.9 s. The fixed cost is the part that does not travel between
# machines, so each one fits its own.
#
# `enhance_seconds` is the enhancer's pass inside a Generate. On 2026-11-20, at 384 x 384 and
# 25 frames, a prompt the enhancer had to lengthen took 9.1 s and one it had written already,
# which skips the pass, 6.5 s; the NVFP4 enhancer with its compiled decode accounts for the 2.6 s.
#
# Refit on 2026-11-19, with the transformer compiled and the decode tiled, on the warm second
# run of 16 clips from 384 x 384 to 1920 x 1088 and 5 to 15 s: 0.426 of the figure plus 13.4 s
# reads each clip within 4%, where 0.530 and 14.2 s read 3 to 26% high. The 384 and 512 rows
# ran before the tiled decode, which moves a decode by under a second.
CLIP_SCALE = 0.426
CLIP_FIXED_SECONDS = 13.4
ENHANCE_SECONDS = 2.6


def ltx25_cuda_estimate() -> VideoEstimate:
    shared = video_estimate("ltx25", "bf16")
    return replace(
        shared,
        scale=CLIP_SCALE,
        pack_factor=1.0,
        fixed_seconds=CLIP_FIXED_SECONDS,
        enhance_seconds=ENHANCE_SECONDS,
    )


def ltx25_cuda_capabilities() -> VideoCapabilities:
    shared = ltx25_mlx_capabilities()
    return replace(
        shared,
        backend_id="ltx25_cuda",
        name="LTX-2.5",
        badge="bf16",
        description="Multishot clips up to 15 s that keep characters and light across cuts, with sound, in bf16 and guided by keyframes. Runs on CUDA.",
        precision="bf16",
        modes=(replace(shared.mode("generate"), accepts_audio=False),),
        adapters=(),
        fast_mode=False,
        estimate=ltx25_cuda_estimate(),
    )
