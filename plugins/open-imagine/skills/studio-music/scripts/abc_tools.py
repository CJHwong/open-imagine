#!/usr/bin/env python3
"""Check the two-voice ABC score a Music backend returns.

Adapted from the YuE2 agent skill's abc_tools.py (Apache License 2.0,
Copyright (c) 2026 the YuE2 authors) and fitted to this studio's score dialect.

    python3 scripts/abc_tools.py inspect score.abc
    python3 scripts/abc_tools.py compare source.abc edited.abc --voices Vocal
    python3 scripts/abc_tools.py manifest --source source.abc --edit edited.abc --output edit_manifest.json
    python3 scripts/abc_tools.py strip-chords score.abc cover.abc --keep-voice Ins

The score is the engine's narrow ABC: header fields, then voice sections of music
lines that end with a plain barline. Times are exact fractions of a quarter note.
This tool checks symbols. It does not hear the render: a matching score does not
prove the performance followed it, and a different score may be the intended edit.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

VOICES = ("Vocal", "Ins")
NATURAL = dict(zip("CDEFGAB", (0, 2, 4, 5, 7, 9, 11), strict=True))
KEY_ORDER = ("FCGDAEB", "BEADGCF")
KEYS = {
    **dict(
        zip(
            ("Cb", "Gb", "Db", "Ab", "Eb", "Bb", "F", "C", "G", "D", "A", "E", "B", "F#", "C#"),
            range(-7, 8),
            strict=True,
        )
    ),
    **dict(
        zip(
            ("Abm", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm", "Am", "Em", "Bm", "F#m", "C#m", "G#m", "D#m", "A#m"),
            range(-7, 8),
            strict=True,
        )
    ),
}
ACCIDENTALS = {"=": 0, "_": -1, "__": -2, "^": 1, "^^": 2}
TOKEN = re.compile(
    r'"(?P<chord>[^"\n]*)"|\[K:(?P<key>[^\]\n]+)\]|'
    r"(?P<acc>\^\^|__|\^|_|=)?(?P<note>[A-Ga-gz])"
    r"(?P<oct>[,']*)(?P<duration>[0-9]+)?(?P<tie>-?)"
)
FIELD = re.compile(r"^(?P<name>[A-Za-z]):(?P<value>.*)$")
METER = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")


class AbcError(ValueError):
    """Unsupported notation or a failed structural invariant."""


def fail(condition: bool, message: str) -> None:
    if condition:
        raise AbcError(message)


def key_accidentals(key: str) -> dict[str, int]:
    fail(key not in KEYS, f"unsupported key {key!r}; use a standard major or minor K: value")
    count = KEYS[key]
    signs = {letter: 0 for letter in NATURAL}
    for letter in KEY_ORDER[0 if count > 0 else 1][: abs(count)]:
        signs[letter] = 1 if count > 0 else -1
    return signs


def meter_value(text: str) -> tuple[int, int]:
    match = METER.fullmatch(text.strip())
    if match is None:
        raise AbcError(f"unsupported meter {text!r}; write an explicit fraction")
    numerator = int(match.group(1))
    denominator = int(match.group(2))
    fail(denominator > 1024 or bool(denominator & (denominator - 1)), f"unsupported meter denominator {denominator}")
    return numerator, denominator


def meter_length(meter: tuple[int, int]) -> Fraction:
    return Fraction(4 * meter[0], meter[1])


def unit_value(text: str) -> Fraction:
    match = re.fullmatch(r"1/([1-9][0-9]*)", text.strip())
    if match is None:
        raise AbcError(f"unsupported unit {text!r}; the engine writes L:1/<power of two>")
    denominator = int(match.group(1) or "0")
    fail(denominator > 1024 or bool(denominator & (denominator - 1)), f"unsupported L: denominator {denominator}")
    return Fraction(1, denominator)


def tempo_value(text: str) -> int:
    match = re.fullmatch(r"(?:1/4=)?([1-9][0-9]*)", text.strip())
    if match is None:
        raise AbcError(f"unsupported tempo {text!r}; write Q:1/4=<BPM>")
    return int(match.group(1) or "0")


@dataclass
class Voice:
    meter: tuple[int, int]
    key: str
    time: Fraction = Fraction(0)
    notes: list = field(default_factory=list)
    bars: list = field(default_factory=list)
    chords: list = field(default_factory=list)
    pending: tuple | None = None


@dataclass
class Score:
    text: str
    title: str
    meter: tuple[int, int]
    key: str
    unit: Fraction
    bpm: int
    voices: dict[str, Voice]
    music_lines: dict[int, str]


def add_note(
    voice: Voice,
    note: str,
    acc: str,
    octave: str,
    units: int,
    tie: bool,
    unit: Fraction,
    offset: Fraction,
    local: dict,
    context: str,
) -> None:
    duration = units * unit * 4
    fail("," in octave and "'" in octave, f"{context}: mixed octave marks")
    length = meter_length(voice.meter)
    fail(offset + duration > length, f"{context}: note runs past the measure end")
    letter = note.upper()
    written = 60 + NATURAL[letter] + (12 if note.islower() else 0)
    written += 12 * (octave.count("'") - octave.count(","))
    alteration = local.get(letter, key_accidentals(voice.key)[letter])
    if acc:
        alteration = ACCIDENTALS[acc]
        local[letter] = alteration
    pitch = written + alteration
    if voice.pending is not None:
        old_pitch, old_written = voice.pending
        # An unmarked continuation keeps the tied accidental across the barline.
        # It does not alter a later untied note in that bar.
        if not acc and written == old_written:
            pitch = old_pitch
        fail(pitch != old_pitch, f"{context}: tie changes pitch from {old_pitch} to {pitch}")
        voice.notes[-1][2] += duration
    else:
        fail(not 0 <= pitch <= 127, f"{context}: pitch {pitch} is outside the MIDI range")
        voice.notes.append([voice.time + offset, pitch, duration])
    voice.pending = (pitch, written) if tie else None


def parse_bar(body: str, voice: Voice, unit: Fraction, context: str) -> None:
    length = meter_length(voice.meter)
    offset = Fraction(0)
    local: dict[str, int] = {}
    if body == "Z":
        fail(voice.pending is not None, f"{context}: tie enters a full-measure rest")
        offset = length
    else:
        cursor = 0
        while cursor < len(body):
            if body[cursor].isspace():
                cursor += 1
                continue
            match = TOKEN.match(body, cursor)
            if match is None:
                raise AbcError(f"{context}: unsupported token at {body[cursor : cursor + 24]!r}")
            cursor = match.end()
            fail(offset >= length, f"{context}: event after the measure end")
            chord = match.group("chord")
            key = match.group("key")
            if chord is not None:
                voice.chords.append((voice.time + offset, chord))
                continue
            if key is not None:
                key_accidentals(key)
                voice.key = key
                local = {}
                continue
            note = match.group("note") or ""
            acc = match.group("acc") or ""
            octave = match.group("oct") or ""
            tie = bool(match.group("tie"))
            units = int(match.group("duration") or "1")
            duration = units * unit * 4
            if note == "z":
                fail(bool(acc or octave or tie), f"{context}: a rest cannot carry an accidental, octave or tie")
                fail(voice.pending is not None, f"{context}: tie enters a rest")
                fail(offset + duration > length, f"{context}: rest runs past the measure end")
                offset += duration
                continue
            add_note(voice, note, acc, octave, units, tie, unit, offset, local, context)
            offset += duration
    fail(offset != length, f"{context}: {offset} quarter notes, but the meter holds {length}")
    voice.bars.append((voice.time, length))
    voice.time += length


def split_bars(line: str, context: str) -> list[str]:
    fail(not line.endswith("|"), f"{context}: the music line must end with a plain barline")
    bars = [bar.strip() for bar in line[:-1].split("|")]
    expanded = []
    for bar in bars:
        fail(not bar, f"{context}: empty measure, or an unsupported double or repeat barline")
        repeat = re.fullmatch(r"Z([2-4])?", bar)
        expanded.extend(["Z"] * int(repeat.group(1) or "1") if repeat else [bar])
    return expanded


def parse(text: str) -> Score:
    """Fail closed on unsupported notation; report sounding notes, not token counts."""
    lines = text.splitlines()
    fail(not lines, "the score is empty")
    meter: tuple[int, int] = (4, 4)
    unit = Fraction(1, 8)
    bpm = 0
    key = "C"
    title = ""
    declared: set[str] = set()
    voices: dict[str, Voice] = {}
    music_lines: dict[int, str] = {}
    current: Voice | None = None
    current_name: str = ""
    # M: and K: may sit before or after the V: line, so hold them until music names the voice.
    pending: list[tuple[str, str]] = []

    def apply_field(name: str, value: str, context: str) -> None:
        nonlocal meter, unit, bpm, key, title, current, current_name
        if name == "X":
            return
        if name == "T":
            title = value.strip()
            return
        if name == "M":
            meter = meter_value(value)
            declared.add("M")
            pending.append(("M", value))
            return
        if name == "L":
            unit = unit_value(value)
            declared.add("L")
            fail(current is not None and current.time != 0, f"{context}: the unit changed after music started")
            return
        if name == "Q":
            bpm = tempo_value(value)
            return
        if name == "K":
            key = value.strip()
            key_accidentals(key)
            declared.add("K")
            pending.append(("K", key))
            return
        if name == "V":
            name_of_voice = value.strip().split()[0] if value.strip() else ""
            fail(not name_of_voice, f"{context}: a V: field needs a voice name")
            fail(not {"M", "L"} <= declared, f"{context}: declare M: and L: before V:")
            # A declaration may come before K:, so start on C and take the key when it arrives.
            voices.setdefault(name_of_voice, Voice(meter, key))
            current = voices[name_of_voice]
            current_name = name_of_voice
            return
        if name in {"W", "w"}:
            fail(True, f"{context}: this dialect has no lyric lines; keep the words in the request")
        fail(True, f"{context}: unsupported header {name}:")

    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        context = f"line {number}"
        field_match = FIELD.match(stripped)
        if field_match:
            apply_field(field_match.group("name"), field_match.group("value"), context)
            continue
        if current is None:
            raise AbcError(f"{context}: music before the first V: field")
        if not {"M", "L"} <= declared:
            raise AbcError(f"{context}: music before M: and L:")
        for name, value in pending:
            if name == "M":
                current.meter = meter_value(value)
            else:
                current.key = value
        pending.clear()
        for bar in split_bars(stripped, context):
            parse_bar(bar, current, unit, f"{context}, bar {len(current.bars) + 1}")
        music_lines[number] = current_name
    for voice in voices.values():
        fail(voice.pending is not None, "the score ends with an unresolved tie")
    fail(not voices, "the score declares no voice")
    scored = [voice for voice in voices.values() if voice.bars]
    fail(not scored, "the score holds no music")
    return Score(text, title, meter, key, unit, bpm, voices, music_lines)


def json_value(value):
    if isinstance(value, Fraction):
        return str(value)
    raise TypeError(type(value).__name__)


def report(score: Score) -> dict:
    return {
        "scope": "symbolic check of the engine's ABC; not audio verification",
        "sha256": hashlib.sha256(score.text.encode()).hexdigest(),
        "title": score.title,
        "meter": f"{score.meter[0]}/{score.meter[1]}",
        "key": score.key,
        "unit": str(score.unit),
        "bpm": score.bpm,
        "seconds": round(float(max(v.time for v in score.voices.values()) * 60 / score.bpm), 2) if score.bpm else None,
        "voices": {
            name: {
                "sounding_notes": len(voice.notes),
                "measures": len(voice.bars),
                "chords": sorted({chord for _, chord in voice.chords}),
                "notes": [
                    {"onset_quarters": str(onset), "midi_pitch": pitch, "duration_quarters": str(length)}
                    for onset, pitch, length in voice.notes
                ],
            }
            for name, voice in score.voices.items()
        },
    }


def first_bar_difference(before: Voice, after: Voice) -> str | None:
    shared = min(len(before.bars), len(after.bars))
    for index in range(shared):
        if before.bars[index] != after.bars[index]:
            return f"bar {index + 1}"
    if len(before.bars) != len(after.bars):
        return f"bar {shared + 1}: {len(before.bars)} bars became {len(after.bars)}"
    return None


def compare(before: Score, after: Score, names=VOICES, allow_tempo_change=False) -> dict:
    differences = []
    changes = {"chords": 0}
    if before.bpm != after.bpm and not allow_tempo_change:
        differences.append(f"tempo {before.bpm} -> {after.bpm}")
    for name in names:
        fail(name not in before.voices or name not in after.voices, f"voice {name!r} is missing from one score")
        old, new = before.voices[name], after.voices[name]
        grid = first_bar_difference(old, new)
        if grid:
            differences.append(f"{name}: {grid}")
        if old.notes != new.notes:
            shared = min(len(old.notes), len(new.notes))
            index = next((i for i in range(shared) if old.notes[i] != new.notes[i]), shared)
            bar = (
                next(
                    (n + 1 for n, (start, length) in enumerate(old.bars) if old.notes[index][0] < start + length),
                    len(old.bars) + 1,
                )
                if index < len(old.notes)
                else len(old.bars) + 1
            )
            differences.append(
                f"{name}: sounding notes differ at note {index + 1} (bar {bar}); "
                f"{len(old.notes)} notes became {len(new.notes)}"
            )
        changes["chords"] += len({chord for _, chord in old.chords} ^ {chord for _, chord in new.chords})
    return {
        "match": not differences,
        "compared_voices": list(names),
        "tempo_change_allowed": allow_tempo_change,
        "differences": differences,
        "chord_symbols_changed": changes["chords"],
        "scope": "exact symbolic notes and meter; no claim about the generated audio",
    }


def bar_position(voice: Voice, onset: Fraction) -> tuple[int, Fraction]:
    for index, (start, length) in enumerate(voice.bars):
        if start <= onset < start + length:
            return index + 1, onset - start
    return len(voice.bars) + 1, onset


def events_by_bar(voice: Voice) -> list[list]:
    starts = [start for start, _ in voice.bars]
    events: list[list] = [[] for _ in voice.bars]
    for onset, pitch, duration in voice.notes:
        index = bisect.bisect_right(starts, onset) - 1
        if 0 <= index < len(events):
            events[index].append((onset - starts[index], pitch, duration))
    return events


def changed_bars(before: Voice, after: Voice) -> list[int]:
    old, new = events_by_bar(before), events_by_bar(after)
    shared = min(len(old), len(new))
    changed = [index + 1 for index in range(shared) if old[index] != new[index]]
    changed.extend(range(shared + 1, max(len(old), len(new)) + 1))
    return changed


def chord_entry(voice: Voice, onset: Fraction, symbol: str) -> dict:
    bar, beat = bar_position(voice, onset)
    return {"bar": bar, "beat": str(beat), "symbol": symbol}


def chord_changes(before: Voice, after: Voice) -> dict:
    old = {(onset, symbol) for onset, symbol in before.chords}
    new = {(onset, symbol) for onset, symbol in after.chords}
    return {
        "added": [chord_entry(after, onset, symbol) for onset, symbol in sorted(new - old)],
        "removed": [chord_entry(before, onset, symbol) for onset, symbol in sorted(old - new)],
    }


def score_summary(score: Score, path: Path) -> dict:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(score.text.encode()).hexdigest(),
        "title": score.title,
        "meter": f"{score.meter[0]}/{score.meter[1]}",
        "key": score.key,
        "unit": str(score.unit),
        "bpm": score.bpm,
    }


def build_manifest(
    source: Score,
    edited: Score,
    source_path: Path,
    edited_path: Path,
    names=VOICES,
    allow_tempo_change=False,
    brief_sha256: str | None = None,
) -> dict:
    """Collect the mechanical evidence of an edit. The invariant level and the reason are yours."""
    voices = {}
    for name in names:
        old, new = source.voices[name], edited.voices[name]
        shared = min(len(old.notes), len(new.notes))
        first = next((index for index in range(shared) if old.notes[index] != new.notes[index]), None)
        if first is not None:
            changed_note = first + 1
        elif len(old.notes) != len(new.notes):
            changed_note = shared + 1
        else:
            changed_note = None
        voices[name] = {
            "before_notes": len(old.notes),
            "after_notes": len(new.notes),
            "changed_bars": changed_bars(old, new),
            "first_changed_note": changed_note,
            "chords": chord_changes(old, new),
        }
    return {
        "source": score_summary(source, source_path),
        "edited": score_summary(edited, edited_path),
        "brief_sha256": brief_sha256,
        "comparison": compare(source, edited, names, allow_tempo_change),
        "voices": voices,
        "scope": "symbolic evidence for one edit; add the invariant level, the permitted changes and the reason",
    }


def strip_chords(text: str, keep_voice="both") -> str:
    source = parse(text)
    lines = text.splitlines(keepends=True)

    def transform(match):
        if match.group("chord") is not None:
            return ""
        silenced = keep_voice not in ("both", source.music_lines[index]) and match.group("note") is not None
        return "z" + (match.group("duration") or "") if silenced else match.group(0)

    for index in source.music_lines:
        lines[index - 1] = TOKEN.sub(transform, lines[index - 1])
    output = "".join(lines)
    result = parse(output)
    names = VOICES if keep_voice == "both" else (keep_voice,)
    changes = compare(source, result, [name for name in names if name in source.voices and name in result.voices])
    fail(not changes["match"], f"removing the chord symbols changed the melody: {changes['differences']}")
    fail(any(voice.chords for voice in result.voices.values()), "a chord symbol survived the removal")
    if keep_voice != "both":
        fail(any(v.notes for name, v in result.voices.items() if name != keep_voice), "a silenced voice still sounds")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="validate a score and print its notes, bars and chord symbols")
    inspect.add_argument("score", type=Path)
    inspect.add_argument("--output", type=Path)
    diff = commands.add_parser("compare", help="check the sounding notes and meter after an edit")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    diff.add_argument("--voices", choices=("both", *VOICES), default="both")
    diff.add_argument("--allow-tempo-change", action="store_true")
    diff.add_argument("--output", type=Path)
    record = commands.add_parser("manifest", help="write the evidence for an edit as JSON")
    record.add_argument("--source", type=Path, required=True)
    record.add_argument("--edit", type=Path, required=True)
    record.add_argument("--brief", type=Path, help="the brief the editor worked from")
    record.add_argument("--voices", choices=("both", *VOICES), default="both")
    record.add_argument("--allow-tempo-change", action="store_true")
    record.add_argument("--output", type=Path)
    strip = commands.add_parser("strip-chords", help="remove chord symbols, as a cover needs")
    strip.add_argument("source", type=Path)
    strip.add_argument("output", type=Path)
    strip.add_argument("--keep-voice", choices=("both", *VOICES), default="both")
    args = parser.parse_args()

    def emit(data: dict) -> None:
        rendered = json.dumps(data, indent=2, ensure_ascii=False, default=json_value) + "\n"
        if args.output:
            fail(args.output.exists(), "the report path already exists; choose a new one")
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")

    try:
        if args.command == "inspect":
            data = report(parse(args.score.read_text(encoding="utf-8")))
            emit(data)
            return 0
        if args.command == "strip-chords":
            fail(args.source.resolve() == args.output.resolve(), "write a new file; do not overwrite the source")
            text = strip_chords(args.source.read_text(encoding="utf-8"), args.keep_voice)
            with args.output.open("x", encoding="utf-8", newline="") as handle:
                handle.write(text)
            print(json.dumps({"output": str(args.output), "kept_voice": args.keep_voice}))
            return 0
        names = VOICES if args.voices == "both" else (args.voices,)
        source_text = (
            args.source.read_text(encoding="utf-8")
            if args.command == "manifest"
            else args.before.read_text(encoding="utf-8")
        )
        edited_text = (
            args.edit.read_text(encoding="utf-8")
            if args.command == "manifest"
            else args.after.read_text(encoding="utf-8")
        )
        source, edited = parse(source_text), parse(edited_text)
        if args.command == "manifest":
            brief_sha256 = hashlib.sha256(args.brief.read_bytes()).hexdigest() if args.brief else None
            emit(build_manifest(source, edited, args.source, args.edit, names, args.allow_tempo_change, brief_sha256))
            return 0
        data = compare(source, edited, names, args.allow_tempo_change)
        emit(data)
        return 1 if data.get("match") is False else 0
    except (AbcError, OSError) as problem:
        print(f"ABC check failed: {problem}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
