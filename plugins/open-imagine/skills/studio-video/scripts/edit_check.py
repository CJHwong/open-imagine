#!/usr/bin/env python3
"""Check the rendered clips and the assembled export against edit.json, before anyone watches the cut.

usage: edit_check.py /abs/edit.json [--export film.mp4] [--text [--expect-text SH14 SH15]] > report.json

Per clip, inside the range the edit uses: the clip covers its slot, no black frames, no
still run longer than a second, and how much the picture still changes in the clip's last
half second (the end-state hold; a number, not a verdict). Across the edit: no two
subtitles overlap. For the export: its length matches the edit, it has audio, and its
true peak stays at or below -1 dBTP; integrated loudness is reported.

--text reads each generated clip (not a shot marked "source": "footage") every TEXT_STEP seconds with the macOS Vision text recognizer
(`uv run --with pyobjc-framework-Vision`). A video model can draw a quoted line into the
picture as a caption; any text found fails unless the shot is listed in --expect-text. OCR also reads shapes as
text (a hand and a glass came back as "2m"); after looking at the frame, pass that one
reading with --accept-text SHOT:TEXT, and the report records it as accepted.

Exit status 1 when any check fails. These checks find mechanical faults only. Acting,
lip sync and story still need a person to watch the cut.
"""

import argparse
import itertools
import json
import math
import pathlib
import re
import subprocess
import sys

FPS = 24
FREEZE_SECONDS = 1.0
HOLD_SECONDS = 0.5
PEAK_LIMIT = -1.0
TEXT_STEP = 0.25


def ffmpeg_log(path, start, seconds, video_filter):
    """Run one detection filter over part of a clip and return ffmpeg's log, where the filters report."""
    return subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-ss",
            f"{start}",
            "-t",
            f"{seconds}",
            "-i",
            str(path),
            "-vf",
            video_filter,
            "-an",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stderr


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    info = json.loads(out)
    return float(info["format"]["duration"]), {s["codec_type"] for s in info["streams"]}


def gray_frame(path, at):
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{max(at, 0)}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=32:56,format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return raw


def finding(check, result, evidence, shot=None, value=None):
    record = {"check": check, "result": result, "evidence": evidence}
    if shot:
        record["shot"] = shot
    if value is not None:
        record["value"] = value
    return record


def check_clip(root, shot):
    path = root / shot["clip"]
    start, seconds, name = shot.get("clip_in", 0), shot["duration"], shot["id"]
    length, _ = probe(path)
    findings = [
        finding(
            "clip_length",
            "pass" if length + 1 / FPS >= start + seconds else "fail",
            f"clip is {length:.2f} s; the edit uses {start:.2f} to {start + seconds:.2f} s",
            name,
        )
    ]
    black = re.findall(
        r"black_start:([\d.]+) black_end:([\d.]+)", ffmpeg_log(path, start, seconds, "blackdetect=d=0.1:pix_th=0.10")
    )
    findings.append(
        finding(
            "black",
            "fail" if black else "pass",
            f"black from {black[0][0]} to {black[0][1]} s into the slot" if black else "no black frames",
            name,
        )
    )
    frozen = re.findall(
        r"freeze_start: ([\d.]+)", ffmpeg_log(path, start, seconds, f"freezedetect=n=0.001:d={FREEZE_SECONDS}")
    )
    findings.append(
        finding(
            "freeze",
            "fail" if frozen else "pass",
            f"picture still for over {FREEZE_SECONDS} s from {float(frozen[0]):.2f} s into the slot"
            if frozen
            else f"no still run over {FREEZE_SECONDS} s",
            name,
        )
    )
    before, after = gray_frame(path, length - HOLD_SECONDS), gray_frame(path, length - 1.5 / FPS)
    change = sum(abs(a - b) for a, b in zip(before, after, strict=True)) / max(len(before), 1)
    findings.append(
        finding("end_hold", "measure", f"mean change over the last {HOLD_SECONDS} s, 0 to 255", name, round(change, 2))
    )
    return findings


def check_subtitles(subtitles):
    ordered = sorted(subtitles, key=lambda s: s["start"])
    findings = [
        finding(
            "subtitle_overlap",
            "fail",
            f"{a['text']!r} ends at {a['end']} s after {b['text']!r} starts at {b['start']} s",
        )
        for a, b in itertools.pairwise(ordered)
        if b["start"] < a["end"]
    ]
    return findings or [finding("subtitle_overlap", "pass", f"{len(ordered)} subtitles, none overlap")]


def text_times(shot, length):
    """Every TEXT_STEP seconds across the slot, then the clip's last frame. A drawn caption can flicker on and off."""
    start, seconds = shot.get("clip_in", 0), shot["duration"]
    last = length - 1.5 / FPS
    # A clip shorter than its slot has no frame past its end; clip_length reports that, OCR must not crash on it.
    return [at for at in (start + step * TEXT_STEP for step in range(math.ceil(seconds / TEXT_STEP))) if at < last] + [
        last
    ]


def text_shots(shots):
    """Generated clips only: real footage shows real signs and screens, which are not model-drawn captions."""
    return [shot for shot in shots if shot.get("source", "generated") == "generated"]


def read_text(root, shots):
    """Return {shot id: [(text, confidence)]} from the frames text_times picks."""
    import Vision
    from Foundation import NSURL

    readings = {}
    for shot in shots:
        path = root / shot["clip"]
        length, _ = probe(path)
        found = []
        for at in text_times(shot, length):
            frame = pathlib.Path("/tmp") / f"edit_check_{shot['id']}_{at:.2f}.png"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{at}", "-i", str(path), "-frames:v", "1", str(frame)],
                check=True,
            )
            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLanguages_(["zh-Hans", "en-US"])
            handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
                NSURL.fileURLWithPath_(str(frame)), None
            )
            ok, error = handler.performRequests_error_([request], None)
            frame.unlink()
            if not ok:
                raise RuntimeError(f"{shot['id']}: text recognition failed: {error}")
            found += [(r.topCandidates_(1)[0].string(), round(r.confidence(), 2)) for r in request.results()]
        readings[shot["id"]] = found
    return readings


def judge_text(readings, expected, accepted=frozenset()):
    """accepted holds (shot, text) readings a person looked at and found to be no text, such as a hand read as "2m"."""
    findings = []
    for name, found in readings.items():
        words = sorted({text for text, _ in found if (name, text) not in accepted})
        cleared = sorted({text for text, _ in found if (name, text) in accepted})
        if cleared and not words:
            findings.append(finding("drawn_text", "pass", f"accepted after review: {', '.join(cleared)}", name))
            continue
        if not words:
            findings.append(finding("drawn_text", "pass", "no text found", name))
        elif name in expected:
            findings.append(finding("drawn_text", "pass", f"expected text: {', '.join(words)}", name))
        else:
            findings.append(finding("drawn_text", "fail", f"text in the picture: {', '.join(words)}", name))
    return findings


def check_export(path, total):
    length, streams = probe(path)
    findings = [
        finding(
            "export_length",
            "pass" if abs(length - total) <= 1 / FPS + 0.05 else "fail",
            f"export is {length:.2f} s; the edit is {total:.2f} s",
        ),
        finding(
            "export_audio",
            "pass" if "audio" in streams else "fail",
            "has an audio stream" if "audio" in streams else "no audio stream",
        ),
    ]
    if "audio" not in streams:
        return findings
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stderr
    summary = log[log.rfind("Summary:") :]
    loudness = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1))
    peak = float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary).group(1))
    findings.append(
        finding(
            "export_peak",
            "pass" if peak <= PEAK_LIMIT else "fail",
            f"true peak {peak} dBTP; the limit is {PEAK_LIMIT} dBTP",
            value=peak,
        )
    )
    findings.append(finding("export_loudness", "measure", "integrated loudness in LUFS", value=loudness))
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("edit", type=pathlib.Path)
    parser.add_argument("--export", type=pathlib.Path, help="The assembled film to check against the edit")
    parser.add_argument("--text", action="store_true", help="Read each clip for drawn text (macOS Vision)")
    parser.add_argument("--expect-text", nargs="*", default=[], help="Shots whose picture is meant to show text")
    parser.add_argument(
        "--accept-text",
        nargs="*",
        default=[],
        metavar="SHOT:TEXT",
        help="A reading a person checked and found to be no text, such as SH06:2m",
    )
    args = parser.parse_args()
    root = args.edit.resolve().parent
    edit = json.loads(args.edit.read_text())
    shots = [shot for shot in edit["shots"] if shot.get("clip")]
    findings = [f for shot in shots for f in check_clip(root, shot)] + check_subtitles(edit.get("subtitles", []))
    if args.text:
        accepted = {tuple(item.split(":", 1)) for item in args.accept_text}
        findings += judge_text(read_text(root, text_shots(shots)), set(args.expect_text), accepted)
    if args.export:
        total = max(shot["start"] + shot["duration"] for shot in edit["shots"])
        findings += check_export(args.export, total)
    problems = [f for f in findings if f["result"] == "fail"]
    print(
        json.dumps(
            {"ok": not problems, "clips": len(shots), "problems": problems, "findings": findings},
            ensure_ascii=False,
            indent=2,
        )
    )
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
