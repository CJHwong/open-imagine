"""What YuE2 offers when it runs on a CUDA GPU.

The modes, limits and settings are the model's, so they come from the same record at every
build. What differs between the two entries is the precision, and with it the badge, the
memory the child holds and the figure the form shows.
"""

from studio.l1_entities.music_capabilities import MusicCapabilities, MusicEstimate

MAX_LYRICS_CHARACTERS = 600
"""How much lyric this engine finishes in one song.

Measured on the DGX Spark on 2026-11-14 with one style and one repeated line: 463
characters sang 84.9 s of audio, 615 characters sang 118.7 s and finished, and 760
characters reached the semantic stage's token budget and produced nothing. The limit is
the measured pass minus a margin. It is calibrated on English lyrics; Chinese is denser,
so a long Chinese lyric can still reach the engine's own error after the run.
"""

# The measured cost on the NVFP4 build, DGX Spark GB10, seed 7, one operation at a time
# through the studio API on 2026-11-15. Warm runs, after the first case paid the load.
# Characters of the lyric, and the wall time:
#
#   33  67.2    272  89.2    413  98.2    483  164.5
#
# A line through those four gives 52.4 s plus 0.175 s per lyric character. It reads 58.2,
# 100.0, 124.6 and 136.9 s, so the worst error is 28 s on a run of 165 s.
#
# That is a wide scatter, and it is the engine's, not the fit's. The time follows the song
# the engine chooses, and that choice is not the lyric length: the 33-character line sang
# 209 s of audio in 67.2 s, and a 60-character Mandarin lyric sang 69 s in 31.1 s.
# `MusicEstimate` reads one line in lyric characters, so this is the shape it can hold, and
# a figure this engine returns can be half or double a short run.
#
# Plan, transcribe and cover run whole stages rather than a song, so they carry one figure
# each. Plan took 9.0 s. Transcribe took 25.7 s and cover 45.5 s on a 20 s reference, both
# warm. The first cover of a fresh studio took 52.1 s, which carries the pinned
# transcriber's install.
#
# An instrumental took 126.8 s warm and 126.1 s on its first run, so this path carries no
# load worth naming. Against the 53.6 s that the line reads for its seven characters, the
# melody it transfers costs 73.2 s.
NVFP4_ESTIMATE = MusicEstimate(
    generate_base_seconds=52.4,
    generate_seconds_per_lyric_character=0.175,
    instrumental_extra_seconds=73.2,
    plan_seconds=9.0,
    cover_seconds=45.5,
    transcribe_seconds=25.7,
)

# The same sweep on the bf16 build, 2026-11-15, warm runs:
#
#   33  117.2    272  137.3    413  318.8    535  202.6
#
# A line through those four gives 108.8 s plus 0.272 s per lyric character. It reads 117.8,
# 182.7, 221.1 and 254.2 s. The 413-character run took 319 s, so the worst error is 98 s.
#
# That scatter is the engine's, and it is wider here than on the pack. The wall time
# follows the song the engine writes, and the songs differ in length: the 413-character
# run sang 444 s of audio in 318.8 s and the 535-character run sang 272 s in 202.6 s. Per
# second of audio the bf16 build takes 0.67 to 0.86 s against the pack's 0.32 to 0.48.
#
# Plan took 17.0 s, cover 126.3 s and transcribe 21.1 s on the same 20 s reference. An
# instrumental took 250.8 s against the 110.7 s that the line reads for its seven characters,
# so the melody costs 140.1 s.
BF16_ESTIMATE = MusicEstimate(
    generate_base_seconds=108.8,
    generate_seconds_per_lyric_character=0.272,
    instrumental_extra_seconds=140.1,
    plan_seconds=17.0,
    cover_seconds=126.3,
    transcribe_seconds=21.1,
)

ESTIMATES = {"bf16": BF16_ESTIMATE, "nvfp4": NVFP4_ESTIMATE}


def yue2_cuda_capabilities(backend_id: str = "yue2_cuda", name: str = "YuE2 (CUDA)", badge: str = "bf16"):
    """The record for one entry. `badge` is the build the child was started with, so a
    section that overrides it shows the figure measured on that build. The fp8 build has no
    sweep of its own, and it measured within 9% of bf16 per second of audio, so it reads the
    bf16 figure."""
    return MusicCapabilities(
        backend_id,
        name,
        badge,
        description="Complete songs from style and lyrics, with melody, chord and cover from a recording.",
        # The engine stops past this count, so the form refuses the same request the engine
        # would. The shared record's 20000 is the model's own figure, not this engine's.
        max_lyrics_characters=MAX_LYRICS_CHARACTERS,
        estimate=ESTIMATES.get(badge, BF16_ESTIMATE),
    )
