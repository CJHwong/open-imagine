"""The Drama-3 controls, on the CUDA engine. The form is the MLX one; the numbers are not."""

from studio.l1_entities.voice_capabilities import (
    Capabilities,
    Estimate,
    LoadingPolicy,
    ModeSpec,
    ParamSpec,
    Template,
)
from studio.l3_interface_adapters.gateways.template_translations import translate_templates
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.template_translations import TRANSLATIONS

SAMPLING = (
    ParamSpec(
        "temperature",
        "number",
        0.7,
        minimum=0.1,
        maximum=1.0,
        step=0.05,
        hint="Higher values vary the performance more.",
    ),
    ParamSpec(
        "top_p",
        "number",
        0.7,
        minimum=0.1,
        maximum=1,
        step=0.05,
        hint="Probability mass retained when choosing the next audio token.",
    ),
    ParamSpec(
        "top_k", "number", 30, minimum=1, maximum=100, integer=True, step=1, hint="Number of candidate audio tokens."
    ),
    ParamSpec(
        "max_tokens",
        "number",
        2048,
        minimum=64,
        maximum=2048,
        integer=True,
        step=1,
        hint="Safety limit per internal script chunk, not a target duration. A limit reached before completion fails the job.",
    ),
)
TRANSCRIPT = ParamSpec("ref_text", "text", "", required=True, hint="Exact words spoken in the reference recording.")
TEMPLATES = (
    Template(
        "Whisper",
        "Direct a quiet delivery without reading the direction aloud.",
        "[whispers] {script}",
        "Delivery",
        (ParamSpec("script", "text", "Keep your voice down. Someone is listening."),),
    ),
    Template(
        "Excited",
        "Direct an enthusiastic delivery.",
        "[excited] {script}",
        "Delivery",
        (ParamSpec("script", "text", "We finally made it! This is wonderful!"),),
    ),
)
TEMPLATES = translate_templates(TEMPLATES, TRANSLATIONS, locale="zh-TW")


# M5 Pro 64 GiB, eight-bit weights, seed 7, native 44.1 kHz, 0.5s codec chunks:
# warm whisper 3.07s audio / 2.72s wall; excited 4.09 / 4.66;
# cached Clone 3.39 / 3.87. Primitive load 20.61s; first generation 16.00s.
#
# The script's length, measured 2026-11-13 on the same machine, through the studio's
# own route, one fresh start for each run. Characters of the script, then the seconds
# of audio it produced:
#
#   25  1.90    111  10.50    275  25.08
#
# A straight line through them gives 0.092 s of audio per character. The 25-character
# run sits 20% under the line and the other two within 3%, so the figure is an "about"
# for a script of any length. A 592-character script hit the engine's token cap before
# it finished, so scripts longer than about 275 characters cannot be measured this way.
#
# The measured cost on this machine, DGX Spark GB10, FP8 weights, seed 7, native 44.1 kHz,
# one operation at a time through the studio API on 2026-11-15. Warm runs, after the
# resident child holds the model. Characters of the script, the audio it produced, and the
# wall time:
#
#   28  3.53 s  5.0      66  6.18 s  9.0      451  34.60 s  48.1
#
# A line through those three gives 1.383 s of work per second of audio and 0.28 s fixed.
# It reads 5.2, 8.8 and 48.1 s, so the worst error is 0.2 s.
#
# The page turns a script into audio seconds with `seconds_per_character`. The three runs
# above produced 0.126, 0.094 and 0.077 s of audio per character, and 0.077 is the value
# that fits the wall time best: it reads 3.3, 8.3 and 48.3 s. The script of a few words
# then reads about 2 s short, which is the price of one line through three lengths.
#
# A fresh server pays one load of about 58 s before its first run: the first case here took
# 63.1 s and ran 5.0 s of work. The figures below are the run, not the load.
#
# Clone measured 5.39 s of audio for a 52-character script in 9.1 s. Its reference costs
# 1.6 s, so it carries its own fixed cost and the audio per character that this voice
# produced, 0.104. One run, not a curve.
ESTIMATE = Estimate(rtf=1.383, overhead=0.28, seconds_per_character=0.077)
CLONE_ESTIMATE = Estimate(rtf=1.383, overhead=1.64, seconds_per_character=0.104)


def drama_cuda_capabilities():
    return Capabilities(
        backend_id="drama3_cuda",
        name="Drama-3 (CUDA)",
        badge="FP8 W8A8",
        description="Expressive speech and voice cloning with delivery cues inside the script.",
        max_batch=16,
        default_mode="generate",
        reference_sample_rate=44100,
        max_reference_seconds=15,
        loading=LoadingPolicy(
            "download_on_first_use",
            "fishaudio/drama-3",
            "78e5ab79e49aa9a25abe8799eff2c4d73a1c3216",
            "The first run downloads about 40 GB of FP8 weights and loads them in about 30 s. Duration follows the script. Delivery cues go inside square brackets.",
        ),
        modes=(
            ModeSpec(
                "generate",
                "Generate",
                SAMPLING,
                text_hint="Write a script. Add delivery cues inline, such as [whispers].",
                templates=TEMPLATES,
                estimate=ESTIMATE,
            ),
            ModeSpec(
                "clone",
                "Clone",
                (*SAMPLING, TRANSCRIPT),
                min_references=1,
                max_references=1,
                text_hint="Write the new words. Inline delivery cues are optional.",
                templates=TEMPLATES,
                estimate=CLONE_ESTIMATE,
            ),
        ),
    )
