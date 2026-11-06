#!/usr/bin/env python3
"""Build a second cut of an edit from the same clips, for a blind A/B of two cuts.

usage: recut.py /abs/edit.json /abs/rows.json /abs/out.json

rows.json:
  {"rows": [{"id": "HOOK-SH08", "source": "SH08", "clip_in": 0.2, "seconds": 1.0, "keep_sound": false}, ...],
   "drop_sounds": ["room-tone"],          # path fragments never carried from the old edit
   "sounds": [{"path": "...", "at": 0.0, "gain": 0.9}],   # added verbatim, in new-cut time
   "titles": [{"text": "...", "start": 2.0, "end": 4.5}]} # the new cut's titles, verbatim; none when absent

Each row takes the source shot's clip from clip_in for its seconds and plays after the row
before it. With keep_sound, the row keeps the sounds and subtitles that start inside the
part of the old slot it shows, moved to the new time. Every other edit field carries over.
"""

import json
import pathlib
import sys


def window(shot, row):
    """The old-edit interval the row's picture came from: the slot, shifted by the change of clip_in."""
    begin = shot["start"] + row["clip_in"] - shot.get("clip_in", 0)
    return begin, begin + row["seconds"]


def carried(row, shot, at, edit, drop):
    """Sounds and subtitles that start inside the row's old interval, moved to the row's new time."""
    if not row["keep_sound"]:
        return [], []
    begin, end = window(shot, row)
    sounds = [
        dict(s, at=round(at + s["at"] - begin, 2))
        for s in edit.get("sounds", [])
        if begin <= s["at"] < end and not any(fragment in s["path"] for fragment in drop)
    ]
    subtitles = [
        dict(s, start=round(at + s["start"] - begin, 2), end=round(at + s["end"] - begin, 2))
        for s in edit.get("subtitles", [])
        if begin <= s["start"] < end
    ]
    return sounds, subtitles


def recut(edit, rows):
    by_id = {shot["id"]: shot for shot in edit["shots"]}
    unknown = sorted({row["source"] for row in rows["rows"]} - by_id.keys())
    if unknown:
        raise ValueError(f"Rows cite shots the edit does not have: {unknown}")
    shots, sounds, subtitles, at = [], [], [], 0.0
    for row in rows["rows"]:
        shot = by_id[row["source"]]
        shots.append(dict(shot, id=row["id"], start=round(at, 2), duration=row["seconds"], clip_in=row["clip_in"]))
        row_sounds, row_subtitles = carried(row, shot, at, edit, rows.get("drop_sounds", []))
        sounds += row_sounds
        subtitles += row_subtitles
        at += row["seconds"]
    sounds += rows.get("sounds", [])
    return dict(edit, shots=shots, sounds=sounds, subtitles=subtitles, titles=rows.get("titles", []))


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    edit_path, rows_path, out_path = map(pathlib.Path, sys.argv[1:])
    out = recut(json.loads(edit_path.read_text()), json.loads(rows_path.read_text()))
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    length = sum(shot["duration"] for shot in out["shots"])
    print(
        f"{out_path}: {len(out['shots'])} shots, {len(out['sounds'])} sounds, {len(out['subtitles'])} subtitles, {length:.1f}s"
    )


if __name__ == "__main__":
    main()
