"""The initial H3 envelope: one short clip, with its own soundtrack."""

from studio.plugins.video import VideoCapabilities, VideoShape

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
    description="Experimental staged MLX generation with synchronized sound. Short clips only.",
    shapes=SHAPES,
    default_shape_ratio="16:9",
    min_frames=73,
    max_frames=124,
    frame_step=17,
    duration_presets=(73, 124),
    default_frames=73,
    frame_rate=24,
    max_references=0,
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
