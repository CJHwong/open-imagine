"""What the MLX q8 video packs offer the form.

Both packs use the same engine at 8 bits on Apple Silicon. Each pack declares its
measured prompt aids and modes here.
"""

from studio.l1_entities.capabilities import Template
from studio.l1_entities.video_capabilities import (
    VideoAdapter,
    VideoCapabilities,
    VideoEstimate,
    VideoMode,
    VideoShape,
)
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_LOOKS, VIDEO_TEMPLATES

# The time of a clip, as `VideoEstimate` reads it. Every figure is provisional.
#
# The shape of a Generate run is an older runner's fit: the Python API of the same MLX port, in
# low-memory mode, from a stress test of a 2.3 finetune at int4 on the M5 Pro with 64 GB on
# 2026-10-17, over 10.9 to 31.6 thousand tokens. An int8 pack took 5.6% longer. It gave
# 87 s for 768 x 512 x 73 and 306 s for 1280 x 704 x 121, against that runner's 86 s and 307 s.
# The CLI that this studio drives is slower, so `scale` and `fixed_seconds` are fitted, by
# relative error, to this studio's own recorded runs of LTX-2.5 q8 on the same machine. The
# prompt pass was on in each of them:
#
#   clip                  measured        fit
#   384 x 384 x 25         91.4 s         102 s    design-decisions.md, audio entry
#   1280 x 704 x 73       393.2 s         312 s    design-decisions.md, two runs of one clip
#   1280 x 704 x 73       499.8 s         312 s
#   1920 x 1088 x 17      248.4 s         227 s    batch.py, per item
#   1920 x 1088 x 97      790.0 s        1007 s    max_dimension below
#
# The 40.9 s for 384 x 384 x 121 under SHAPES is left out: it is shorter than the 91.4 s of a
# shorter clip at that size, so the two runs did not pay the same loads, and neither says which.
#
# No run timed the prompt pass alone. The 15 s for it is the time that an enhancer of the same
# size took before a clip in the older studio. A LoRA added about 7 s to a 3 s clip at 480p,
# and two added 25 s to a 5 s clip at 1080p, in the older runner: 10 s each. An audio track
# took 243.4 s against 91.4 s for the same clip, about 2.5 times, on the guided path. A
# keyframe on 2.3 takes the same guided path, so it takes the same factor, unmeasured.
#
# An effect is fitted on its own: seconds = a + b x thousands of tokens of the output, from the
# portrait and landscape checks of PROMPTS.md through /api/v1/videos/edit:
#
#   effect           output             measured     fit
#   Day to night     448 x 768 x 97      338.0 s     318 s
#   Day to night     768 x 448 x 97      273.3 s     318 s
#   Deblur           544 x 960 x 121     850.9 s     760 s
#   Decompression    544 x 960 x 121     544.0 s     760 s
#   Clean plate      576 x 1024 x 49     324.5 s     279 s
#   Restore          544 x 960 x 97      633.1 s     582 s
#   Water            704 x 1280 x 97    1376.9 s    1142 s
#   Water            1280 x 704 x 97     958.8 s    1142 s
#
# Upscale 2x sits off that fit: 986.1 s for a 768 x 1280 x 121 output, 0.62 of the fit's
# 1598 s. Layout to Render has no timed run, so it takes the fit as it is.
GENERATE_LOAD = (2.33, 0.874)
GENERATE_STAGE_1 = (2.037, 0.1260)
GENERATE_STAGE_2 = (2.628, 0.08134)
GENERATE_DECODE = (-10.44, 0.3331)
GENERATE_SCALE = 1.46
GENERATE_FIXED_SECONDS = 87.0
ENHANCE_SECONDS = 15.0
LORA_SECONDS = 10.0
GUIDED_FACTOR = 2.5
EDIT_SECONDS = (-190.5, 116.45)
UPSCALE_COST = 0.62
# The fit holds int4. An int8 pack, such as both base packs, takes 5.6% longer.
PACK_FACTORS = {"int4": 1.0, "int8": 1.056}
EXCLUDES = ("weight download", "queue wait")


def video_estimate(family: str, precision: str) -> VideoEstimate:
    """The constants of a pack of this family at this precision. A precision that no run
    measured takes the int8 figure."""
    return VideoEstimate(
        load=GENERATE_LOAD,
        stage_1=GENERATE_STAGE_1,
        stage_2=GENERATE_STAGE_2,
        decode=GENERATE_DECODE,
        scale=GENERATE_SCALE,
        pack_factor=PACK_FACTORS.get(precision, PACK_FACTORS["int8"]),
        fixed_seconds=GENERATE_FIXED_SECONDS,
        enhance_seconds=ENHANCE_SECONDS,
        lora_seconds=LORA_SECONDS,
        guided_factor=GUIDED_FACTOR,
        # The runner takes the two-stage path for a keyframe on 2.3 only.
        guided_with_references=family == "ltx23",
        edit=EDIT_SECONDS,
        excludes=EXCLUDES,
    )


# These three first fills reproduce the API probes from 2026-10-20. The sideways and
# orbit probes also moved forward, so they do not earn separate templates.
_CAMERA_SCENE = (
    "[Subject] rests on [surface]. [Foreground object] stands closer to the camera, "
    "and [background object] stands behind [subject name]. [light]. "
)
LTX25_TEMPLATES = (
    *VIDEO_TEMPLATES,
    Template(
        "Speak to camera",
        "One speaker, quoted words, fixed camera",
        "A front-facing medium close-up shows [speaker] against [background]. [light]. "
        '[Subject pronoun] looks into the lens and clearly says in [language], "[dialogue]" '
        "[Possessive pronoun] lips and jaw move naturally with each word. "
        "The camera stays fixed throughout the continuous shot. "
        "[Possessive pronoun] voice is clear over [sound].",
    ),
    Template(
        "Fixed composition",
        "A still subject with a fixed camera",
        _CAMERA_SCENE + "The camera stays fixed, holding the same composition. One continuous shot with [sound].",
    ),
    Template(
        "Slow push-in",
        "Move closer while the subject stays still",
        _CAMERA_SCENE
        + "The camera slowly moves toward [subject name], ending in a closer view while [subject name] stays still. "
        "One continuous shot with [sound].",
    ),
)

# The rungs the 22B model renders. Every side is a multiple of 64 and every shape follows
# the image form's own. Only 384 x 384 and 121 frames was timed on the q8 packs: 40.9 s from
# text on 2.5, 39.7 s on 2.3, and 45.1 s for a two keyframe run on 2.3. The remaining rungs
# are the model's declared sizes, not measurements of this engine.
SHAPES = (
    VideoShape("1:1", 384, 384),
    VideoShape("1:1", 512, 512),
    VideoShape("1:1", 768, 768),
    VideoShape("16:9", 640, 384),
    VideoShape("16:9", 768, 448),
    VideoShape("16:9", 1024, 576),
    VideoShape("16:9", 1280, 704),
    VideoShape("16:9", 1920, 1088),
    VideoShape("9:16", 384, 640),
    VideoShape("9:16", 448, 768),
    VideoShape("9:16", 576, 1024),
    VideoShape("9:16", 1088, 1920),
    VideoShape("3:2", 768, 512),
    VideoShape("3:2", 960, 640),
    VideoShape("3:2", 1152, 768),
    VideoShape("2:3", 512, 768),
    VideoShape("2:3", 640, 960),
    VideoShape("2:3", 768, 1152),
)


# Existing effects retain their measured single-stage recipes (2026-10-20).
# Layout to Render uses its own two-stage recipe. Its earlier mosaic was traced
# to the port silently leaving its upscaler untrained when v1_1 was absent;
# the dedicated child requires the LTX-2.5 pack's v1_0 weights (2026-10-23).
DAY_TO_NIGHT_PROMPT = (
    "A realistic nighttime scene of the same place: deep blue moonlight, warm street lamps "
    "and lit shop windows, deep natural shadows. Only the lighting changes from day to "
    "night; identical composition, framing, camera movement and motion."
)
WATER_SIMULATION_PROMPT = (
    "ADD WATER. A sudden downpour floods the same shot, water running along every surface and "
    "splashing underfoot, the same composition and the same subjects. One continuous shot."
)
CLEAN_PLATE_PROMPT = (
    "The same shot with nobody in it: the place empty, the same setting and the same light, "
    "with the people, the animals and the vehicles gone. One continuous shot."
)
DEBLUR_PROMPT = (
    "DEBLUR. The same shot, sharp and in focus, every edge crisp and the texture of each "
    "surface visible. One continuous shot."
)
DECOMPRESSION_PROMPT = (
    "ENHANCE QUALITY. The same shot with clean edges, no blocking or banding, honest colour. One continuous shot."
)
RESTORE_PROMPT = (
    "The same shot as a clean, colour, high-resolution capture: natural colour and skin "
    "tones, sharp detail, stable frames, no scratches, no dust, no flicker, no sepia cast. "
    "One continuous shot."
)
UPSCALE_PROMPT = (
    "The same shot at twice the width and height: crisp edges, fine texture and natural "
    "detail, no blur, no ringing. One continuous shot."
)

VIDEO_ADAPTERS = (
    VideoAdapter(
        id="custom",
        label="Custom",
        hint="No LoRA: experimental clip conditioning with your own prompt; source fidelity may vary",
        mode="edit",
        file="",
        min_strength=1.0,
        max_strength=1.0,
    ),
    VideoAdapter(
        id="layout-to-render",
        label="Layout to Render",
        hint="Turn a layout animation into a finished shot. Add a look image made from its first frame; describe the finished materials and lighting.",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors",
        stage_2_conditioning=True,
        min_references=1,
        max_references=1,
        reference_frame_index=0,
        card="Layout-To-Render",
    ),
    VideoAdapter(
        id="day-to-night",
        label="Day to night",
        hint="Relight a daylight clip as the same shot at night",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-day-to-night-0.9.safetensors",
        prompt=DAY_TO_NIGHT_PROMPT,
        width=768,
        height=448,
        num_frames=97,
        card="Day-To-Night",
    ),
    VideoAdapter(
        id="water-simulation",
        label="Water simulation",
        hint="Flood the same shot: rain, standing water, splashes underfoot",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-water-simulation-0.9.safetensors",
        prompt=WATER_SIMULATION_PROMPT,
        # The card's production size is 1920 x 1088. This pair is the one measured: at
        # 1280 x 704 a daylight room floods, the floor becomes water and the splash shows at
        # the feet. At 960 x 544, the card's dev-base validation size, no water appeared
        # (2026-10-20). At 1920 x 1088 the single-stage path runs out of Metal memory on a
        # 64 GB Mac, so the shipped pair is the largest that fits.
        width=1280,
        height=704,
        num_frames=97,
        card="Water-Simulation",
    ),
    VideoAdapter(
        id="clean-plate",
        label="Clean plate",
        hint="Empty the shot: people and vehicles gone, the place kept",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors",
        prompt=CLEAN_PLATE_PROMPT,
        width=1024,
        height=576,
        num_frames=49,
        card="Clean-Plate",
    ),
    VideoAdapter(
        id="deblur",
        label="Deblur",
        hint="Sharpen a soft or out of focus clip",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-deblur-0.9.safetensors",
        prompt=DEBLUR_PROMPT,
        width=960,
        height=544,
        num_frames=121,
        card="Deblur",
    ),
    VideoAdapter(
        id="decompression",
        label="Decompression",
        hint="Clean up a clip crushed by heavy compression",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-decompression-0.9.safetensors",
        prompt=DECOMPRESSION_PROMPT,
        width=960,
        height=544,
        num_frames=121,
        card="Decompression",
    ),
    VideoAdapter(
        id="restore",
        label="Restore",
        hint="Clean up old or damaged footage: colour, sharpness, no noise",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-restore-1.0.safetensors",
        prompt=RESTORE_PROMPT,
        width=960,
        height=544,
        num_frames=97,
        card="Restore",
    ),
    VideoAdapter(
        id="upscale-2x",
        label="Upscale 2x",
        hint="Render the same shot at twice the width and height",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
        prompt=UPSCALE_PROMPT,
        doubles_output=True,
        card="Pixel-Spatial-Upscaler",
        cost_factor=UPSCALE_COST,
    ),
)


FAMILIES = {"ltx25": "LTX-2.5", "ltx23": "LTX-2.3"}


def _capabilities(
    backend_id: str,
    name: str,
    family: str,
    *,
    edit: bool = False,
    audio: bool = True,
    fast_mode: bool = False,
    aids: bool = True,
    description: str = "Native MLX on Apple Silicon, 8-bit weights.",
    precision: str = "int8",
) -> VideoCapabilities:
    """Both families share the sizes and the timing, and the 2.5 family adds its camera
    templates. `aids` offers the Looks and the templates, sampled on the two base packs only."""
    generate = VideoMode(
        "generate",
        "Generate",
        accepts_audio=audio,
        looks=VIDEO_LOOKS if aids else (),
        min_references=0,
        max_references=8,
        prompt_label="Prompt",
        placeholder="Describe how the subject should look and move.",
        run_label="Generate video",
    )
    edit_mode = VideoMode(
        "edit",
        "Edit",
        needs_clip=True,
        min_references=0,
        max_references=0,
        prompt_label="What to change",
        placeholder="Pick an effect, then describe the change.",
        run_label="Edit clip",
    )
    return VideoCapabilities(
        backend_id=backend_id,
        name=name,
        badge="24 fps",
        description=description,
        precision=precision,
        fast_mode=fast_mode,
        shapes=SHAPES,
        default_shape_ratio="1:1",
        min_frames=9,
        max_frames=361,
        frame_step=8,
        duration_presets=(121, 241, 361),
        default_frames=121,
        frame_rate=24,
        max_references=8,
        min_reference_strength=0.05,
        max_reference_strength=1.0,
        reference_strength_step=0.05,
        default_reference_strength=1.0,
        min_seed=0,
        max_seed=2**32 - 1,
        # The port accepts any side on the 64 pixel grid; the form keeps its own bounds so a
        # typo cannot ask for a shape the model was never sampled at.
        min_dimension=256,
        # 1080p class. Measured on the M5 Pro: a 1920 x 1088 generate of 97 frames
        # took 790 s on 2.5 q8 and stayed inside 64 GB, on the distilled two-stage path.
        max_dimension=1920,
        dimension_step=64,
        templates=((LTX25_TEMPLATES if family == "ltx25" else VIDEO_TEMPLATES) if aids else ()),
        modes=(generate, edit_mode) if edit else (generate,),
        adapters=VIDEO_ADAPTERS if edit else (),
        estimate=video_estimate(family, precision),
    )


def ltx25_mlx_capabilities() -> VideoCapabilities:
    return _capabilities("ltx25_mlx", "LTX-2.5", "ltx25", edit=True, fast_mode=True)


def ltx23_mlx_capabilities() -> VideoCapabilities:
    return _capabilities("ltx23_mlx", "LTX-2.3", "ltx23")


def ltx_pack_capabilities(
    backend_id: str,
    name: str,
    family: str,
    *,
    description: str = "",
    precision: str = "int8",
    edit: bool = False,
    audio: bool = False,
    fast_mode: bool = False,
) -> VideoCapabilities:
    """A pack that a plugin names: the base packs' sizes and timing, and no prompt aids.

    The Looks and the templates were sampled on the base packs only, so a pack offers none
    of them until someone samples it too. Edit, an audio track and Fast mode are off unless
    the plugin turns them on: none of them was run on a finetune. Only the 2.5 family has
    the effects and Fast mode.
    """
    if family not in FAMILIES:
        raise ValueError(f"an LTX pack's family is {' or '.join(FAMILIES)}, not {family!r}")
    if edit and family != "ltx25":
        raise ValueError("only an ltx25 pack can offer Edit, because the effects are LTX-2.5 adapters")
    if fast_mode and family != "ltx25":
        raise ValueError("only an ltx25 pack can offer Fast mode, because it was measured on LTX-2.5")
    return _capabilities(
        backend_id,
        name,
        family,
        edit=edit,
        audio=audio,
        fast_mode=fast_mode,
        aids=False,
        description=description or f"An {FAMILIES[family]} pack on the studio's MLX engine.",
        precision=precision,
    )
