# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Prove edit_check.py catches each fault: plant one known fault per copy and expect exactly its own check to fail.

usage: negative_controls.py /abs/edit.json SHOT [--export film.mp4] [--caption TEXT] [--font FONT.ttf]

A clean result proves nothing unless the checker fails on a broken input. One production's
caption passed a four-point text check, because the caption flickered between the samples.
Each control copies one clean clip (or the clean export), plants one fault, and runs
edit_check.py on the copy. A control behaves when the planted fault's check fails and no
other check fails. The drawn_text control needs the macOS Vision recognizer through `uv`;
without it, the control is reported as skipped, never as passed.

Exit status 1 when any control misbehaves.
"""

import argparse
import json
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

EDIT_CHECK = pathlib.Path(__file__).resolve().parent / "edit_check.py"
sys.path.insert(0, str(EDIT_CHECK.parent))
import edit_check  # noqa: E402

CLIP_FAULTS = ("black", "freeze", "drawn_text", "clip_length")
CAPTION = "Caption drawn by the video model"


def ffmpeg(*arguments):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, arguments)], check=True)


def video_info(path):
    """Return (width, height, frames per second) of the first video stream."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    stream = json.loads(out)["streams"][0]
    numerator, denominator = stream["r_frame_rate"].split("/")
    return stream["width"], stream["height"], float(numerator) / float(denominator)


def caption_card(path, width, height, caption, font_path=None):
    """A transparent frame with one white subtitle-style line, like a caption the video model drew."""
    size = max(width // 14, 10)
    font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size=size)
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(card).text(
        (width * 0.08, height * 0.72), caption, fill="white", font=font, stroke_width=2, stroke_fill="black"
    )
    card.save(path)


def plant(fault, clip, out, at, scratch, caption=CAPTION, font_path=None):
    """Write a copy of the clip with one fault around `at` seconds."""
    width, height, fps = video_info(clip)
    if fault == "black":
        ffmpeg(
            "-i",
            clip,
            "-vf",
            f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,{at},{at + 0.3})'",
            "-c:a",
            "copy",
            out,
        )
    elif fault == "freeze":
        # Hold one frame for 1.5 s, then carry on: the clip keeps its length and loses its motion there.
        length, _ = edit_check.probe(clip)
        ffmpeg(
            "-i",
            clip,
            "-vf",
            f"loop=loop={round(1.5 * fps)}:size=1:start={round(at * fps)},trim=duration={length}",
            "-c:a",
            "copy",
            out,
        )
    elif fault == "drawn_text":
        # 0.3 s of caption: short enough to fall between sparse samples.
        card = scratch / "card.png"
        caption_card(card, width, height, caption, font_path)
        ffmpeg(
            "-i",
            clip,
            "-i",
            card,
            "-filter_complex",
            f"[0][1]overlay=enable='between(t,{at},{at + 0.3})'",
            "-c:a",
            "copy",
            out,
        )
    elif fault == "clip_length":
        ffmpeg("-i", clip, "-t", "1.0", out)
    else:
        raise ValueError(f"Unknown fault {fault!r}")


def vision_available():
    return platform.system() == "Darwin" and shutil.which("uv") is not None


def run_edit_check(edit, scratch, *extra):
    """Run edit_check.py on an edit; return the sorted names of the failed checks."""
    path = scratch / "edit.json"
    path.write_text(json.dumps(edit, ensure_ascii=False))
    runner = (
        ["uv", "run", "-q", "--with", "pyobjc-framework-Vision", "python"] if "--text" in extra else [sys.executable]
    )
    run = subprocess.run([*runner, str(EDIT_CHECK), str(path), *extra], capture_output=True, text=True)
    if not run.stdout.strip():
        raise RuntimeError(f"edit_check gave no report: {run.stderr}")
    return sorted({finding["check"] for finding in json.loads(run.stdout)["problems"]})


def clip_controls(shot, root, scratch, caption, font_path):
    """Return (name, expected failures, actual failures or None when skipped) for the clean clip and each clip fault."""
    text = ["--text"] if vision_available() else []
    clean = scratch / "clean.mp4"
    shutil.copy(root / shot["clip"], clean)
    middle = shot.get("clip_in", 0) + shot["duration"] / 2
    results = [
        (
            "none (clean clip)",
            [],
            run_edit_check({"shots": [dict(shot, clip=str(clean))], "subtitles": []}, scratch, *text),
        )
    ]
    for fault in CLIP_FAULTS:
        if fault == "drawn_text" and not text:
            results.append((fault, [fault], None))
            continue
        planted = scratch / f"{fault}.mp4"
        plant(fault, clean, planted, middle, scratch, caption, font_path)
        results.append(
            (
                fault,
                [fault],
                run_edit_check({"shots": [dict(shot, clip=str(planted))], "subtitles": []}, scratch, *text),
            )
        )
    overlapping = [{"text": "a", "start": 1.0, "end": 2.0}, {"text": "b", "start": 1.5, "end": 2.5}]
    results.append(
        (
            "subtitle_overlap",
            ["subtitle_overlap"],
            run_edit_check({"shots": [dict(shot, clip=str(clean))], "subtitles": overlapping}, scratch),
        )
    )
    return results


def export_controls(edit, root, export, scratch):
    """The full edit against copies of the export, each with one fault. Only the export checks are under test here."""
    full = dict(edit, shots=[dict(s, clip=str(root / s["clip"])) for s in edit["shots"] if s.get("clip")])
    length, _ = edit_check.probe(export)
    peak = next(f["value"] for f in edit_check.check_export(export, length) if f["check"] == "export_peak")
    boost = max(edit_check.PEAK_LIMIT - peak, 0) + 3
    faults = {
        "none (clean export)": ([], []),
        "export_length": (["export_length"], ["-t", f"{length - 1.0}", "-c", "copy"]),
        "export_audio": (["export_audio"], ["-an", "-c:v", "copy"]),
        "export_peak": (["export_peak"], ["-af", f"volume={boost:.1f}dB", "-c:v", "copy"]),
    }
    results = []
    for name, (expected, arguments) in faults.items():
        copy = scratch / f"export-{name.split()[0]}{export.suffix}"
        ffmpeg("-i", export, *arguments, copy) if arguments else shutil.copy(export, copy)
        failed = run_edit_check(full, scratch, "--export", str(copy))
        results.append((name, expected, [f for f in failed if f.startswith("export_")]))
    return results


def report(results):
    """Print one row per control; return how many behaved and how many were skipped."""
    print(f"{'planted fault':22} {'expected to fail':20} {'failed':30} result")
    behaved = skipped = 0
    for name, expected, failed in results:
        if failed is None:
            skipped += 1
            outcome, shown = "skipped (no macOS Vision)", "-"
        else:
            behaved += failed == expected
            outcome, shown = ("ok" if failed == expected else "WRONG"), ",".join(failed) or "-"
        print(f"{name:22} {','.join(expected) or '-':20} {shown:30} {outcome}")
    print(f"{behaved} of {len(results) - skipped} controls behave" + (f"; {skipped} skipped" if skipped else ""))
    return behaved, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("edit", type=pathlib.Path)
    parser.add_argument("shot", help="The shot whose clip gets the clip faults")
    parser.add_argument("--export", type=pathlib.Path, help="The clean assembled film for the export controls")
    parser.add_argument("--caption", default=CAPTION, help="The text the drawn_text control burns in")
    parser.add_argument("--font", help="A font file that can draw the caption; needed for non-Latin text")
    args = parser.parse_args()
    root = args.edit.resolve().parent
    edit = json.loads(args.edit.read_text())
    shot = next((s for s in edit["shots"] if s["id"] == args.shot), None)
    if shot is None or not shot.get("clip"):
        sys.exit(f"{args.shot}: no shot with a clip in {args.edit}")
    with tempfile.TemporaryDirectory() as folder:
        scratch = pathlib.Path(folder)
        results = clip_controls(shot, root, scratch, args.caption, args.font)
        if args.export:
            results += export_controls(edit, root, args.export.resolve(), scratch)
    behaved, skipped = report(results)
    sys.exit(0 if behaved == len(results) - skipped else 1)


if __name__ == "__main__":
    main()
