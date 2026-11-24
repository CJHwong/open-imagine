"""MiniMax H3 on the CUDA engine: diffusers' modular blocks, NVFP4 weights.

The form is the released checkpoint's, not the MLX backend's. diffusers takes a still only as
the first or the last frame, and a clip from 5 to 15 seconds, so the 3 s preset and the mid-clip
keyframes of the MLX backend have no place here. Pictures of what to show and an audio track go
through the `ref2va` workflow, which takes no keyframe and refuses a track alone.
"""

from dataclasses import replace

from studio.l1_entities.video_capabilities import VideoCapabilities, VideoEstimate, VideoMode, VideoShape

# 50 sigma points, which is 49 transformer calls: the default of diffusers and of SGLang alike.
# It is a default, not a limit of the weights: the MLX backend runs the same base checkpoint at
# eight calls. No shorter schedule was tried here. Fast mode runs 20 on the same weights.
# Measured on the DGX Spark on 2026-11-20, seed 42, a first and last frame at 20 steps looked no
# worse than text at 50.
STEPS = 50
FAST_STEPS = 20
# HyperFlow H3 Flash samples 4, 6 or 8 transformer calls on its own grid, 6 by default. On the
# DGX Spark on 2026-11-24, at 512 x 288 and 124 frames, six calls took 2.8 s each for text and
# 17.0 s for two pictures, against 3.3 s and 18.8 s for one base call.
FLASH_STEPS = 6
# At 24 fps the pipeline refuses under 120 frames or over 360, after rounding up to 17n + 5:
# 73 and 97 were refused on 2026-11-20. 124 is the first count on that grid, 345 the last.
MIN_FRAMES = 124
MAX_FRAMES = 345
MAX_STILLS = 2
# `ref2va` takes up to nine pictures. It also takes three clips, which the studio does not offer:
# on 2026-11-24 one clip took 22 times a text run at 512 x 288 and copied the clip's own scene
# over the picture beside it, and three clips ran the Spark out of memory even at 288p.
MAX_PICTURES = 9

# Measured on the DGX Spark on 2026-11-21 through the Studio API: text, seed 7, sound on, Fast
# mode (19 forwards), warm, one run at a time. A step is the gap between two step reports; the
# tail is the time after the last forward, which is the decode and the mux.
#
#   size          frames  tokens  step    tail    total   this fit at 19 forwards
#   512 x 288      124     2.30    3.30 s  16.3 s   79.5 s   80.6 s
#   512 x 512      124     4.10    6.14 s  27.6 s  145.0 s  150.3 s
#   1024 x 576     124     9.22   17.86 s  40.9 s  380.8 s  400.8 s
#   1280 x 704     124    14.08   33.09 s  87.5 s  716.7 s  711.1 s
#   512 x 288      345     6.34   11.52 s  51.8 s  271.3 s  250.8 s
#
# A forward costs 1.248 N + 0.0781 N^2 seconds over N thousand latent tokens, counted on the
# LTX grid of `video_estimate.tokens`. The decode costs 4.9 s plus 0.70 s per megapixel of all
# the frames. The fit reads each run within 8%. The figure counts the 49 forwards of a full run;
# Fast mode takes 19, which the figure names and does not count. A picture and a track ran 4.4
# times a text clip at 512 x 288 (360.6 s against 82.3 s), and a first and last frame added 8%.
#
# Pictures without a track, seed 7, two 512 x 512 pictures, through a scratch copy of the child
# driven directly rather than the studio, on 2026-11-23 and 2026-11-24:
#
#   size          frames  forwards  total   per forward  tokens it solves to
#   512 x 288      124       49     992 s     19.87 s        9.85
#   1024 x 576     124       19     873 s     42.96 s       16.79
#
# Less the clip's own 2.30 and 9.22 thousand tokens, each picture adds 3.77 and 3.79 thousand:
# a picture is encoded at its own size, so its cost does not move with the clip.
ESTIMATE = VideoEstimate(
    load=(0.0, 0.0),
    stage_1=(0.0, 0.0),
    stage_2=(1.248, 0.0781),
    decode=(4.9, 0.70),
    fixed_seconds=0.6,
    guided_factor=4.4,
    picture_tokens=3.78,
    forwards=STEPS - 1,
    excludes=("weight download", "queue wait", "the first load, about 135 s", "keyframe rows"),
)

GENERATE = VideoMode(
    "generate",
    "Generate",
    accepts_audio=True,
    max_references=MAX_STILLS,
    max_pictures=MAX_PICTURES,
    keyframes_at_ends=True,
    reference_audio=True,
    placeholder="Describe the scene, the motion and the sound.",
)

# The MLX backend's canvases. 1280 x 704 stays under the pipeline's area cap, 768 x 1344.
SHAPES = (
    VideoShape("16:9", 512, 288),
    VideoShape("16:9", 1024, 576),
    VideoShape("16:9", 1280, 704),
    VideoShape("9:16", 288, 512),
    VideoShape("9:16", 576, 1024),
    VideoShape("9:16", 704, 1280),
    VideoShape("1:1", 512, 512),
)

# The cost, DGX Spark GB10, encoder and both transformers in NVFP4 W4A4, 124 frames, through
# diffusers directly rather than the studio, 2026-11-20. The seconds are one transformer call.
#
#   text,    512 x 288    3.4 s    (FP8: 7.7 s)
#   text,   1024 x 576   17.9 s    (FP8: 34.6 s)
#   picture and track, 512 x 288   17.5 to 19.2 s
#
# A reference run costs five times a text run of the same size: the picture and the track are
# rows of the same sequence. ESTIMATE above holds the fit.
CAPABILITIES = VideoCapabilities(
    backend_id="minimax_h3_cuda",
    name="MiniMax H3",
    badge="NVFP4, 24 fps",
    description=(
        "MiniMax's 33B omni-modal model: 5 to 14 s clips with stereo sound and dialogue, from text, "
        "a first or last frame, or up to 9 pictures and an audio track. Runs on CUDA."
    ),
    shapes=SHAPES,
    default_shape_ratio="16:9",
    min_frames=MIN_FRAMES,
    max_frames=MAX_FRAMES,
    frame_step=17,
    duration_presets=(124, 243, 345),
    default_frames=MIN_FRAMES,
    frame_rate=24,
    modes=(GENERATE,),
    max_references=MAX_STILLS,
    min_reference_strength=1.0,
    max_reference_strength=1.0,
    reference_strength_step=1.0,
    default_reference_strength=1.0,
    min_seed=0,
    max_seed=2**32 - 1,
    min_dimension=256,
    max_dimension=1280,
    dimension_step=32,
    precision="nvfp4",
    fast_mode=True,
    # The page's zh-TW table repeats this text under label.fastmode.minimax_h3_cuda. Change both.
    fast_mode_note="Runs 20 denoise steps instead of 50 on the same weights. Faster; details and motion may differ.",
    audio_track_note=(
        "Turn off to generate a silent video and skip audio processing. An audio track steers the sound the "
        "model generates; the clip is not timed to the track and does not carry it."
    ),
    can_skip_audio=True,
    estimate=ESTIMATE,
)


def minimax_h3_cuda_capabilities() -> VideoCapabilities:
    return CAPABILITIES


FLASH_CAPABILITIES = replace(
    CAPABILITIES,
    backend_id="minimax_h3_flash_cuda",
    name="HyperFlow H3 Flash",
    badge="NVFP4, 6 steps, 24 fps",
    description=(
        "Video Rebirth's pruned H3, under half the size, in six steps: 5 to 14 s clips with stereo sound, "
        "from text, a first or last frame, or up to 9 pictures and an audio track. Runs on CUDA."
    ),
    fast_mode=False,
    fast_mode_note="",
    estimate=None,
)


def flash_capabilities() -> VideoCapabilities:
    return FLASH_CAPABILITIES
