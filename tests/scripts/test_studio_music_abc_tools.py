"""CPU-only checks for the Studio Music score tool."""

import importlib.util
import sys
from fractions import Fraction
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "studio_music_abc_tools",
    Path(__file__).parents[2] / "plugins/open-imagine/skills/studio-music/scripts/abc_tools.py",
)
assert SPEC and SPEC.loader
abc_tools = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = abc_tools  # dataclasses resolve their module through sys.modules
SPEC.loader.exec_module(abc_tools)

SCORE = (
    "X:1\nT:Melody\nM:4/4\nL:1/4\nQ:1/4=100\n"
    'V: Vocal clef=treble name="Vocal Melody"\nV: Ins clef=treble name="Instrumental"\nK:C\n'
    '% verse\nV: Vocal\n"C"C2E2|"Am"G2E2|\n'
    "V: Ins\nC,2G,2|A,2E,2|\n"
)


def test_inspect_reports_sounding_notes_and_chord_symbols():
    data = abc_tools.report(abc_tools.parse(SCORE))
    assert data["meter"] == "4/4" and data["bpm"] == 100
    assert data["voices"]["Vocal"]["sounding_notes"] == 4
    assert data["voices"]["Vocal"]["chords"] == ["Am", "C"]
    assert data["voices"]["Vocal"]["notes"][0] == {
        "onset_quarters": "0",
        "midi_pitch": 60,
        "duration_quarters": "2",
    }


def test_a_chord_only_edit_keeps_the_melody():
    edited = SCORE.replace('"Am"', '"Am7"')
    result = abc_tools.compare(abc_tools.parse(SCORE), abc_tools.parse(edited))
    assert result["match"] is True and result["chord_symbols_changed"] == 2


def test_a_pitch_edit_names_the_note_and_the_bar():
    edited = SCORE.replace('"C"C2E2', '"C"C2F2', 1)
    result = abc_tools.compare(abc_tools.parse(SCORE), abc_tools.parse(edited), ("Vocal",))
    assert result["match"] is False
    assert result["differences"] == ["Vocal: sounding notes differ at note 2 (bar 1); 4 notes became 4"]


def test_a_bar_that_exceeds_the_meter_fails():
    with pytest.raises(abc_tools.AbcError, match="event after the measure end"):
        abc_tools.parse(SCORE.replace("C,2G,2|", "C,2G,2G,2|", 1))


def test_an_unresolved_tie_fails():
    score = SCORE.replace("C,2G,2|A,2E,2|", "C,4|E,4-|", 1)
    with pytest.raises(abc_tools.AbcError, match="unresolved tie"):
        abc_tools.parse(score)


def test_strip_chords_keeps_the_melody_and_can_silence_one_voice():
    cover = abc_tools.strip_chords(SCORE, "Ins")
    parsed = abc_tools.parse(cover)
    assert parsed.voices["Ins"].notes == abc_tools.parse(SCORE).voices["Ins"].notes
    assert parsed.voices["Vocal"].notes == []
    assert not any(voice.chords for voice in parsed.voices.values())


def test_a_meter_change_at_a_section_boundary_is_allowed():
    score = SCORE.replace("V: Ins\n", "M:3/4\nV: Ins\n").replace("C,2G,2|A,2E,2|", "C,2G,|A,2E,|", 1)
    parsed = abc_tools.parse(score)
    assert parsed.voices["Ins"].bars == [(Fraction(0), Fraction(3)), (Fraction(3), Fraction(3))]
