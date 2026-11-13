from studio.l1_entities.music_capabilities import MusicCapabilities, MusicEstimate

# Measured on the office M5 Pro with 64 GiB on 2026-11-12, one run each, through the
# studio's own child. Seconds for the whole request:
#
#   generate, 33 lyric characters     160.2
#   generate, 3048 lyric characters   237.9
#   generate, instrumental            283.2
#   plan, 18 lyric characters          10.1
#   cover, 5 s reference               18.2
#   transcribe, 10 s and 14.6 s         7.1 and 5.1
#
# The two generate rows give 159.4 s plus 0.0258 s per lyric character. The instrumental
# row is the same line plus 123.8 s for the melody plan it transfers. Transcribe does not
# grow with the reference in these two rows, so its figure is the mean, 6.1 s. One run per
# case, so the figure is a band, not a curve.
ESTIMATE = MusicEstimate(
    generate_base_seconds=159.4,
    generate_seconds_per_lyric_character=0.0258,
    instrumental_extra_seconds=123.8,
    plan_seconds=10.1,
    cover_seconds=18.2,
    transcribe_seconds=6.1,
)


def yue2_capabilities():
    return MusicCapabilities(
        "yue2",
        "YuE2",
        "Q8 AR / BF16 audio",
        description="Complete songs from style and lyrics, with editable melody and chords.",
        estimate=ESTIMATE,
    )
