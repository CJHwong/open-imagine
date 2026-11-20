"""MiniMax H3 on the CUDA engine: diffusers' modular blocks, NVFP4 weights.

The form is the released checkpoint's, not the MLX backend's. diffusers takes a still only as
the first or the last frame, and a clip from 5 to 15 seconds, so the 3 s preset and the mid-clip
keyframes of the MLX backend have no place here. An audio track goes through the `ref2va`
workflow, which also takes the stills as pictures of what to show, and refuses a track alone.
"""

from studio.l1_entities.video_capabilities import VideoCapabilities, VideoMode, VideoShape

# The released checkpoint takes 50 sigma points, which is 49 transformer calls: the default of
# diffusers and of SGLang alike. The weights are guidance-distilled, not step-distilled, so 50
# is the model's own setting. Fast mode runs 20 on the same weights. Measured on the DGX Spark
# on 2026-11-20, seed 42, a first and last frame at 20 steps looked no worse than text at 50.
STEPS = 50
FAST_STEPS = 20
# At 24 fps the pipeline refuses under 120 frames or over 360, after rounding up to 17n + 5:
# 73 and 97 were refused on 2026-11-20. 124 is the first count on that grid, 345 the last.
MIN_FRAMES = 124
MAX_FRAMES = 345
MAX_STILLS = 2

GENERATE = VideoMode(
    "generate",
    "Generate",
    accepts_audio=True,
    max_references=MAX_STILLS,
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
# rows of the same sequence. Three sizes are not measured yet, so no estimate is declared.
CAPABILITIES = VideoCapabilities(
    backend_id="minimax_h3_cuda",
    name="MiniMax H3",
    badge="NVFP4, 24 fps",
    description=(
        "MiniMax's 33B omni-modal model: 5 to 14 s clips with stereo sound and dialogue, from text, "
        "a first or last frame, or pictures with an audio track. Runs on CUDA."
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
)


def minimax_h3_cuda_capabilities() -> VideoCapabilities:
    return CAPABILITIES
