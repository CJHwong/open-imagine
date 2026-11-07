"""The H3 envelope: one short clip with its own soundtrack, from text, keyframes or a track."""

from studio.plugins.video import VideoCapabilities, VideoMode, VideoShape

# A still at frame 0 is the first frame, and a still on any later frame is a keyframe there.
# Three were measured on 2026-11-07 on an M5 Pro with 64 GiB, at 512 x 288 and 73 frames.
# Through the Studio API, a first frame, a keyframe at frame 36 and a last frame took 100 s,
# against 75.6 s for text. A spike that drove the worker directly saw a 27.0 GiB MLX peak.
MAX_KEYFRAMES = 3

GENERATE = VideoMode(
    "generate",
    "Generate",
    accepts_audio=True,
    max_references=MAX_KEYFRAMES,
    placeholder="Describe the scene, the motion and the sound.",
)

SHAPES = (
    VideoShape("16:9", 512, 288),
    VideoShape("16:9", 1024, 576),
    VideoShape("9:16", 288, 512),
    VideoShape("9:16", 576, 1024),
    VideoShape("1:1", 512, 512),
)

CAPABILITIES = VideoCapabilities(
    backend_id="minimax_h3",
    name="MiniMax H3",
    badge="Q8 · 24 fps",
    description=(
        "Experimental staged MLX generation with synchronized sound. Short clips only. "
        "Keyframes set the first, a middle or the last frame, and a track drives the motion and becomes the sound."
    ),
    shapes=SHAPES,
    default_shape_ratio="16:9",
    min_frames=73,
    max_frames=124,
    frame_step=17,
    duration_presets=(73, 124),
    default_frames=73,
    frame_rate=24,
    modes=(GENERATE,),
    max_references=MAX_KEYFRAMES,
    min_reference_strength=1.0,
    max_reference_strength=1.0,
    reference_strength_step=1.0,
    default_reference_strength=1.0,
    min_seed=0,
    max_seed=2**32 - 1,
    min_dimension=256,
    max_dimension=1024,
    dimension_step=32,
    precision="int8",
)
