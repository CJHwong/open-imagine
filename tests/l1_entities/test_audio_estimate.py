"""The voice and music figures are the forms' own, split into stages."""

import pytest

from studio.l1_entities.audio_estimate import EXCLUDES, estimate_song, estimate_speech
from studio.l1_entities.estimate_stages import Stage
from studio.l1_entities.music_capabilities import MusicEstimate
from studio.l1_entities.voice_capabilities import Estimate, ModeSpec, ParamSpec
from studio.l1_entities.voice_job import ReferenceAudio, SpeechJob

SECONDS = ParamSpec(id="seconds", kind="number", default=0, minimum=0, maximum=60)
SCRIPTED = ModeSpec("generate", "Generate", (), estimate=Estimate(rtf=1.5, overhead=2.0, seconds_per_character=0.1))
TIMED = ModeSpec("design", "Design", (SECONDS,), estimate=Estimate(rtf=2.0, overhead=1.0, seconds_per_character=0.1))
SONG = MusicEstimate(100.0, 0.02, 120.0, 10.1, 18.2, 6.1)


def job(text="x" * 50, seconds=None, references=0):
    options = {} if seconds is None else {"seconds": seconds}
    return SpeechJob("generate", text, 7, options, (ReferenceAudio(b"", 3.0, 24000),) * references)


def test_a_script_reads_the_length_of_speech_it_produces():
    estimate = estimate_speech(SCRIPTED, job(references=1))

    # 50 characters at 0.1 s each is 5 s of speech: 2 + 1.5 x 5.
    assert (estimate.basis, estimate.reference_count, estimate.audio_seconds) == ("constants", 1, 5.0)
    assert (estimate.setup_seconds, estimate.per_item_seconds, estimate.total_seconds) == (2.0, 7.5, 9.5)
    assert estimate.stages == (Stage("fixed", 2.0), Stage("generation", 7.5))
    assert estimate.excludes == EXCLUDES


def test_a_mode_with_a_length_reads_it_and_not_the_script():
    assert estimate_speech(TIMED, job(seconds=4.0)).total_seconds == 9.0
    assert estimate_speech(TIMED, job(seconds=0)).basis == "unavailable"


def test_no_constants_or_no_length_names_no_seconds():
    plain = ModeSpec("generate", "Generate", ())
    unmeasured = ModeSpec("generate", "Generate", (), estimate=Estimate(rtf=1.0, overhead=1.0))

    for mode in (plain, unmeasured):
        estimate = estimate_speech(mode, job())
        assert (estimate.basis, estimate.total_seconds, estimate.stages) == ("unavailable", None, ())


def test_the_declared_parts_of_the_voice_overhead_are_stages():
    parts = (Stage("prefill", 1.5), Stage("vocoder", 0.5))
    mode = ModeSpec("generate", "Generate", (), estimate=Estimate(1.5, 2.0, 0.1, fixed_parts=parts))

    assert estimate_speech(mode, job()).stages == (*parts, Stage("generation", 7.5))
    with pytest.raises(ValueError, match="overhead parts add up"):
        Estimate(1.5, 2.0, fixed_parts=(Stage("prefill", 1.0),))


def test_a_song_splits_its_base_from_its_lyrics_and_its_melody_plan():
    song = estimate_song(SONG, "generate", "y" * 500, instrumental=True)

    # 100 + 0.02 x 500 + 120.
    assert (song.setup_seconds, song.per_item_seconds, song.total_seconds) == (100.0, 130.0, 230.0)
    assert song.stages == (Stage("fixed", 100.0), Stage("generation", 130.0))
    assert (song.audio_seconds, song.reference_count) == (None, 0)


def test_the_other_music_modes_have_one_figure_each():
    cover = estimate_song(SONG, "cover", "", instrumental=False)

    assert (cover.total_seconds, cover.reference_count) == (18.2, 1)
    assert cover.stages == (Stage("fixed", 0.0), Stage("generation", 18.2))
    assert estimate_song(SONG, "remix", "", False).basis == "unavailable"
    assert estimate_song(None, "generate", "", False).total_seconds is None


def test_the_declared_parts_of_the_song_base_split_generate_only():
    parts = (Stage("load the planner", 60.0), Stage("plan", 40.0))
    split = MusicEstimate(100.0, 0.0, 0.0, 10.0, 18.0, 6.0, fixed_parts=parts)

    assert estimate_song(split, "generate", "", False).stages == (*parts, Stage("generation", 0.0))
    assert estimate_song(split, "plan", "", False).stages == (Stage("fixed", 0.0), Stage("generation", 10.0))
    with pytest.raises(ValueError, match="generate base parts add up"):
        MusicEstimate(100.0, 0.0, 0.0, 10.0, 18.0, 6.0, fixed_parts=parts[:1])
