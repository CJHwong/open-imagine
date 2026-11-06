# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Blind A/B of two cuts: build frame-sheet packets with hidden sides, then unblind the reviewers' verdicts.

usage:
  blind_ab.py pack --a FILM EDIT LABEL --b FILM EDIT LABEL --seed N --out /abs/packet [--step 0.5]
  blind_ab.py verdicts /abs/packet.key.json reviewer1.json reviewer2.json ...

pack samples each film every --step seconds into one sheet, with each time label drawn inside
its own frame, and writes the cut's timing, subtitles, titles and sounds as text. The sides are
named X and Y by a hash of the seed and both films, so the maker cannot pick them. The key goes
beside the packet folder, never inside it. Give each reviewer the packet folder only.

A reviewer answers with JSON:
  {"prefer": "X, Y or none", "reason": "...",
   "findings": [{"side": "X", "frames": [start_s, end_s], "observation": "what the frames show"}]}
verdicts rejects a finding without a frame range or with a range outside its cut, then prints
each reviewer's choice and findings under the real cut labels.
"""

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

COLUMNS = 10
TILE_WIDTH = 144

LIMITS = """You compare two cuts of the same short film, X and Y, from frame sheets and text.
Each sheet shows the cut every {step} s, left to right, top to bottom. The time label inside
each frame is the time of that frame. The text file lists the cuts, subtitles, titles and sounds.

Frame sheets cannot show sound, music, the mix, motion, speed, lip sync, acting, or pacing as
it feels in real time. Read the sound list as text. Mark anything that depends on those as
unassessable. Do not guess it.

1. Narrate what happens in each cut, in a few plain sentences.
2. Say where each cut first made you want to know what happens next, and where you got lost.
3. Say which cut tells the story more clearly and holds attention better, or none.

Every finding cites its frames as a time range from the labels. Answer with JSON only:
{{"prefer": "X, Y or none", "reason": "...",
 "findings": [{{"side": "X", "frames": [start_s, end_s], "observation": "what the frames show"}}]}}
"""


def file_sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def sides(seed, digest_a, digest_b):
    """Return the side names (for cut A, for cut B), chosen by a hash the maker cannot steer."""
    flip = hashlib.sha256(f"{seed}:{digest_a}:{digest_b}".encode()).digest()[0] % 2
    return ("Y", "X") if flip else ("X", "Y")


def film_length(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return float(out)


def label(frame, text):
    """Draw the time label inside the frame's top-left corner; return its box."""
    draw = ImageDraw.Draw(frame)
    font = ImageFont.load_default(size=max(frame.width // 8, 10))
    _, _, right, bottom = draw.textbbox((4, 4), text, font=font)
    box = (0, 0, min(right + 4, frame.width), min(bottom + 4, frame.height))
    draw.rectangle(box, fill="black")
    draw.text((4, 4), text, fill="white", font=font)
    return box


def frames(film, step, scratch):
    """Sample the film every `step` seconds; return the frame images in time order."""
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(film),
            "-vf",
            f"fps=1/{step},scale={TILE_WIDTH}:-2",
            str(scratch / "f%05d.png"),
        ],
        check=True,
    )
    return [Image.open(path).convert("RGB") for path in sorted(scratch.glob("f*.png"))]


def sheet(images, step):
    """Lay the labelled frames out in rows of COLUMNS."""
    width, height = images[0].size
    rows = -(-len(images) // COLUMNS)
    out = Image.new("RGB", (width * COLUMNS, height * rows), "white")
    for index, image in enumerate(images):
        label(image, f"{index * step:.1f}s")
        out.paste(image, ((index % COLUMNS) * width, (index // COLUMNS) * height))
    return out


def cut_text(edit, length):
    """The cut's timing, subtitles, titles and sounds, as the reviewer reads them."""
    lines = [f"length {length:.1f} s", "cuts at: " + ", ".join(f"{s['start']:.1f}" for s in edit["shots"])]
    for kind in ("subtitles", "titles"):
        lines.append(f"{kind}:")
        lines += [f"  {s['start']:.1f}-{s['end']:.1f} s  {s['text']}" for s in edit.get(kind, [])]
    lines.append("sounds:")
    lines += [
        f"  {s['at']:.1f} s  {pathlib.Path(s['path']).stem}"
        for s in sorted(edit.get("sounds", []), key=lambda s: s["at"])
    ]
    return "\n".join(lines) + "\n"


def pack(film_a, edit_a, label_a, film_b, edit_b, label_b, seed, out, step=0.5):
    """Write the packet folder and its key; return the key path."""
    out = pathlib.Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} already holds files; give an empty or new folder")
    out.mkdir(parents=True, exist_ok=True)
    cuts = [(film_a, edit_a, label_a), (film_b, edit_b, label_b)]
    names = sides(seed, file_sha256(film_a), file_sha256(film_b))
    key = {"seed": seed, "sides": {}, "lengths": {}, "films": {}}
    for side, (film, edit, cut_label) in zip(names, cuts, strict=True):
        length = film_length(film)
        with tempfile.TemporaryDirectory() as folder:
            sheet(frames(film, step, pathlib.Path(folder)), step).save(out / f"cut-{side}.png")
        (out / f"cut-{side}.txt").write_text(cut_text(json.loads(pathlib.Path(edit).read_text()), length))
        key["sides"][side] = cut_label
        key["lengths"][side] = round(length, 2)
        key["films"][side] = {"path": str(pathlib.Path(film).resolve()), "sha256": file_sha256(film)}
    (out / "README.txt").write_text(LIMITS.format(step=step))
    key_path = out.parent / f"{out.name}.key.json"
    key_path.write_text(json.dumps(key, indent=2))
    return key_path


def check_finding(finding, key, reviewer):
    side, span = finding.get("side"), finding.get("frames")
    if side not in key["sides"]:
        raise ValueError(f"{reviewer}: a finding names side {side!r}; use X or Y")
    if not (isinstance(span, list) and len(span) == 2 and all(isinstance(t, int | float) for t in span)):
        raise ValueError(f"{reviewer}: every finding needs a frame range [start_s, end_s]: {finding}")
    if not 0 <= span[0] <= span[1] <= key["lengths"][side]:
        raise ValueError(f"{reviewer}: frames {span} lie outside cut {side}, which is {key['lengths'][side]} s long")


def tally(key, verdicts):
    """Validate each reviewer's verdict and return choices and findings under the real cut labels."""
    preferred, reviewers = {}, {}
    for reviewer, verdict in verdicts.items():
        choice = verdict.get("prefer")
        if choice not in (*key["sides"], "none"):
            raise ValueError(f"{reviewer}: prefer must be X, Y or none, not {choice!r}")
        for finding in verdict.get("findings", []):
            check_finding(finding, key, reviewer)
        cut = key["sides"].get(choice, "none")
        preferred[cut] = preferred.get(cut, 0) + 1
        reviewers[reviewer] = {
            "prefer": cut,
            "reason": verdict.get("reason", ""),
            "findings": [dict(f, cut=key["sides"][f["side"]]) for f in verdict.get("findings", [])],
        }
    return {"preferred": preferred, "reviewers": reviewers}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    packer = sub.add_parser("pack")
    packer.add_argument("--a", nargs=3, required=True, metavar=("FILM", "EDIT", "LABEL"))
    packer.add_argument("--b", nargs=3, required=True, metavar=("FILM", "EDIT", "LABEL"))
    packer.add_argument("--seed", type=int, required=True)
    packer.add_argument("--out", type=pathlib.Path, required=True)
    packer.add_argument("--step", type=float, default=0.5)
    reader = sub.add_parser("verdicts")
    reader.add_argument("key", type=pathlib.Path)
    reader.add_argument("verdicts", type=pathlib.Path, nargs="+")
    args = parser.parse_args()
    if args.command == "pack":
        key_path = pack(*args.a, *args.b, args.seed, args.out, args.step)
        print(f"packet {args.out}; key {key_path} (keep the key from the reviewers)")
        return
    key = json.loads(args.key.read_text())
    verdicts = {path.stem: json.loads(path.read_text()) for path in args.verdicts}
    try:
        print(json.dumps(tally(key, verdicts), ensure_ascii=False, indent=2))
    except ValueError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
