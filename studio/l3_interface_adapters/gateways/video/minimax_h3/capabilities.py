"""The H3 envelope: one short clip with its own soundtrack, from text, keyframes or a track."""

from dataclasses import dataclass, replace

from studio.l1_entities.video_capabilities import VideoCapabilities, VideoEstimate, VideoMode, VideoShape

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

# The base schedule has nine sigma points, so eight transformer evaluations. Fast mode runs
# four on the same weights. On 2026-11-09, on an M5 Pro with 64 GiB, seven 1024 x 576 clips of
# 124 frames, each from one still, took about 417 s at four against 754 s at eight, with the
# same 29.2 GiB worker peak. The engine's authors found that a shorter schedule fails first on
# long clips, so Fast mode takes no clip with more video rows than the ones measured. A still
# adds one latent frame of rows, the same count as the memory gate's `_h3_rows`.
BASE_FORWARDS = 8
FAST_FORWARDS = 4
FAST_MAX_ROWS = (37 + 1) * (1024 // 32) * (576 // 32)


def video_rows(width, height, frames, stills):
    """The packed video rows of a clip: 17n + 5 frames make 5n + 2 latent frames of 32-pixel cells,
    and each still adds one more latent frame."""
    return ((frames - 5) // 17 * 5 + 2 + stills) * (width // 32) * (height // 32)


# 1280 x 704 is the high quality class. It is LTX's own 16:9 size, 2.3 percent wide, so a clip
# from either model has the same frame. Its short side stays under H3's released 768 pixels.
SHAPES = (
    VideoShape("16:9", 512, 288),
    VideoShape("16:9", 1024, 576),
    VideoShape("16:9", 1280, 704),
    VideoShape("9:16", 288, 512),
    VideoShape("9:16", 576, 1024),
    VideoShape("9:16", 704, 1280),
    VideoShape("1:1", 512, 512),
)

# 175 frames is 7.3 s at 24 fps. Measured on 2026-11-07 on the same machine through the Studio API,
# at 512 x 288: text took 187 s, and a first frame, a last frame and a voice track took 209 s.
# One page run each at 175 frames: 1024 x 576 took 1,258 s with a 32.9 GiB worker footprint in the
# denoise, and 1280 x 704 took 2,541 s with 39.3 GiB. In the 1280 x 704 run, macOS free memory
# fell by about 48.6 GiB at its lowest. Other shapes have runs only at 512 x 288. On a 64 GiB
# Mac the studio's memory gate refuses 175 frames at 1280 x 704 and takes up to 158.
CAPABILITIES = VideoCapabilities(
    backend_id="minimax_h3",
    name="MiniMax H3",
    badge="Q8, 24 fps",
    description="Experimental short videos with synchronized sound, guided by keyframes or audio.",
    shapes=SHAPES,
    default_shape_ratio="16:9",
    min_frames=73,
    max_frames=175,
    frame_step=17,
    duration_presets=(73, 124, 175),
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
    max_dimension=1280,
    dimension_step=32,
    precision="int8",
    fast_mode=True,
    # The page's zh-TW table repeats this text under label.fastmode.minimax_h3. Change both.
    fast_mode_note=(
        "Runs half the denoise steps on the same weights. Faster; generated details and motion "
        "may differ. Takes clips up to the size of 1024 x 576 at 124 frames with one keyframe."
    ),
)

# HyperFlow H3 Flash: H3 distilled to six steps, with three blocks fewer. It takes a track and the
# LoRAs of base H3 by the user's decision on 2026-11-11, and no run tried either on its weights:
# a LoRA trained on base H3 can fit the distilled weights badly. Fast mode stays off.
FLASH_FORWARDS = 6

# Fitted to five text runs through the Studio API on 2026-11-11: M5 Pro 64 GiB, Q8, seed 42, six
# steps, sound on, one run at a time. The seconds are the wall time of the request.
#
#   size         frames  tokens  measured  this fit
#   512 x 288      73     1.44      59 s      56 s
#   512 x 512     124     4.10     170 s     176 s
#   768 x 448     124     5.38     247 s     248 s
#   768 x 448     175     7.39     388 s     379 s
#   1024 x 576    124     9.22     511 s     515 s
#
# A step costs 3.92 N + 0.454 N^2 seconds over N thousand latent tokens. N is the count of
# `video_estimate.tokens`, on the LTX grid: a measure of the clip's size, not H3's own rows. The decode costs 0.8 s
# for each megapixel of all the frames: a spike run timed it at 26.8 s for 512 x 512 at 124
# frames. The rest, 8 s, is the text encoder and the loads. The formula has no term for a
# keyframe, and a keyframe adds rows: one first frame took 181 s at 512 x 512, and a first and
# a last frame took 277 s at 768 x 448. So a figure is 6 to 12% low for a clip with keyframes.
FLASH_ESTIMATE = VideoEstimate(
    load=(0.0, 0.0),
    stage_1=(0.0, 0.0),
    stage_2=(3.92, 0.454),
    decode=(0.0, 0.8),
    fixed_seconds=8.0,
    forwards=FLASH_FORWARDS,
)

FLASH_CAPABILITIES = replace(
    CAPABILITIES,
    backend_id="minimax_h3_flash",
    name="HyperFlow H3 Flash",
    badge="Q8 · 6 steps · 24 fps",
    description=(
        "Experimental H3 distilled to six steps, with synchronized sound. Short clips only. "
        "Keyframes set the first, a middle or the last frame, and a track drives the motion and becomes the sound. "
        "A track and a LoRA are untested on these weights."
    ),
    fast_mode=False,
    fast_mode_note="",
    estimate=FLASH_ESTIMATE,
)


@dataclass(frozen=True)
class Variant:
    """One model on the H3 engine: its record, the name in its messages, the folder of its
    transformer under the model folder, and the transformer evaluations of its schedule."""

    capabilities: VideoCapabilities
    name: str
    pack: str
    forwards: int
    flash: bool = False


BASE = Variant(CAPABILITIES, "H3", "h3-dit-q8", BASE_FORWARDS)
FLASH = Variant(FLASH_CAPABILITIES, "H3 Flash", "h3-flash-dit-q8", FLASH_FORWARDS, flash=True)
