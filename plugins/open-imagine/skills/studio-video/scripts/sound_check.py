#!/usr/bin/env python3
"""Measure every dialogue take and effect file a project plays, for the sound check reviewer.

usage: sound_check.py /abs/project.json [--words] > measures.json

Per file: length, median pitch, pitch range (10th to 90th percentile, in semitones),
pauses inside the speech and loudness range. Per line it adds the written direction and
whether the take fits its shot. --words transcribes each line with faster-whisper
(`uv run --with faster-whisper --with "av<14" --with pypinyin`; newer av breaks faster-whisper)
so the reviewer can compare words with the script. For Chinese lines it also gives the
toneless pinyin of the script and of the transcription: the transcriber picks characters
for sounds, so a name can come back as a homophone (赵浩 as 招号) with the same sounds.

These numbers show a flat delivery, a missing hesitation or one voice repeated. They
cannot judge acting; the producer's listening does that.
"""

import argparse
import array
import json
import math
import pathlib
import re
import statistics
import subprocess

RATE = 8000
FRAME = 320  # 40 ms
HOP = 160  # 20 ms
LOWEST_HZ, HIGHEST_HZ = 60, 400
PAUSE_SECONDS = 0.15


def decode(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
        check=True,
        capture_output=True,
    ).stdout
    return array.array("h", raw)


def frame_pitch(frame):
    """Autocorrelation pitch of one frame, or None when the frame is not clearly periodic."""
    energy = sum(x * x for x in frame)
    if not energy:
        return None
    best_lag, best = 0, 0.0
    for lag in range(RATE // HIGHEST_HZ, RATE // LOWEST_HZ + 1):
        score = sum(frame[i] * frame[i + lag] for i in range(len(frame) - lag)) / energy
        if score > best:
            best_lag, best = lag, score
    return RATE / best_lag if best > 0.5 else None


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def pauses(loud):
    """Runs of quiet frames between the first and last loud frame, as durations in seconds."""
    if True not in loud:
        return []
    first, last = loud.index(True), len(loud) - 1 - loud[::-1].index(True)
    runs, quiet = [], 0
    for is_loud in loud[first : last + 1]:
        if is_loud and quiet:
            runs.append(quiet * HOP / RATE)
        quiet = 0 if is_loud else quiet + 1
    return [run for run in runs if run >= PAUSE_SECONDS]


def measure(path):
    samples = decode(path)
    frames = [samples[i : i + FRAME] for i in range(0, max(1, len(samples) - FRAME + 1), HOP)]
    levels = [math.sqrt(sum(x * x for x in f) / len(f)) if len(f) else 0.0 for f in frames]
    peak = max(levels, default=0.0)
    loud = [level > peak * 0.1 and level > 30 for level in levels]
    pitches = [hz for f, is_loud in zip(frames, loud, strict=True) if is_loud and (hz := frame_pitch(f))]
    gaps = pauses(loud)
    loud_db = [20 * math.log10(level) for level, is_loud in zip(levels, loud, strict=True) if is_loud]
    return {
        "seconds": round(len(samples) / RATE, 2),
        "voiced_share": round(len(pitches) / max(1, sum(loud)), 2),
        "median_hz": round(statistics.median(pitches)) if pitches else None,
        "pitch_range_semitones": round(12 * math.log2(percentile(pitches, 0.9) / percentile(pitches, 0.1)), 1)
        if pitches
        else None,
        "pauses": len(gaps),
        "longest_pause_seconds": round(max(gaps), 2) if gaps else 0.0,
        "loudness_range_db": round(percentile(loud_db, 0.9) - percentile(loud_db, 0.1), 1) if loud_db else None,
    }


def transcribe(paths):
    from faster_whisper import WhisperModel  # ty: ignore[unresolved-import] - optional, loaded only with --words

    model = WhisperModel("small", device="cpu", compute_type="int8")
    return {path: "".join(s.text for s in model.transcribe(str(path), beam_size=5)[0]).strip() for path in paths}


def sounds(text):
    """Toneless pinyin of the Chinese characters in a text, or None when it has none."""
    characters = re.sub(r"[^\u4e00-\u9fff]", "", text or "")
    if not characters:
        return None
    from pypinyin import lazy_pinyin  # ty: ignore[unresolved-import] - optional, loaded only with --words

    return " ".join(lazy_pinyin(characters))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=pathlib.Path)
    parser.add_argument("--words", action="store_true", help="Transcribe each line with faster-whisper")
    args = parser.parse_args()
    root = args.project.resolve().parent
    project = json.loads(args.project.read_text())
    lines, effects = [], []
    for shot in project["shots"]:
        for line in shot.get("dialogue", []):
            if not line.get("audio"):
                lines.append({"shot": shot["id"], "line": line.get("line"), "problem": "no selected take"})
                continue
            measures = measure(root / line["audio"])
            fits = line.get("at", 0) + measures["seconds"] <= shot["duration"] + 0.05
            lines.append(
                {
                    "shot": shot["id"],
                    "speaker": line.get("speaker"),
                    "line": line.get("line"),
                    "direction": line.get("direction"),
                    "audio": line["audio"],
                    "fits_shot": fits,
                    **measures,
                }
            )
        effects += [{"shot": shot["id"], "audio": path, **measure(root / path)} for path in shot.get("sound_files", [])]
    if args.words:
        heard = transcribe([root / line["audio"] for line in lines if line.get("audio")])
        for line in lines:
            if line.get("audio"):
                line["heard"] = heard[root / line["audio"]]
                if sounds(line["line"]):
                    line["line_sounds"], line["heard_sounds"] = sounds(line["line"]), sounds(line["heard"])
    print(json.dumps({"lines": lines, "effects": effects}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
