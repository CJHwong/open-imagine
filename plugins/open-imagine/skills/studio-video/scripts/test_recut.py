#!/usr/bin/env python3
"""Tests for recut.py: a second cut built from the same clips by a rows file."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import recut

SCRIPT = pathlib.Path(__file__).resolve().parent / "recut.py"

EDIT = {
    "size": [720, 1280],
    "shots": [
        {"id": "SH01", "start": 0.0, "duration": 4.0, "clip": "a.mp4", "clip_in": 0},
        {"id": "SH02", "start": 4.0, "duration": 3.0, "clip": "b.mp4", "clip_in": 0.5},
    ],
    "sounds": [
        {"path": "audio/line1.wav", "at": 0.5, "gain": 1.0},
        {"path": "audio/door.wav", "at": 3.5, "gain": 0.8},
        {"path": "audio/line2.wav", "at": 4.2, "gain": 1.0},
        {"path": "audio/room-tone.wav", "at": 0, "gain": 0.1},
    ],
    "subtitles": [{"text": "one", "start": 0.5, "end": 1.5}, {"text": "two", "start": 4.2, "end": 5.0}],
    "titles": [{"text": "Old title", "start": 0, "end": 2}],
}


class RecutTest(unittest.TestCase):
    def test_rows_take_their_slots_in_order_and_keep_other_edit_fields(self):
        out = recut.recut(
            EDIT,
            {
                "rows": [
                    {"id": "B", "source": "SH02", "clip_in": 0.5, "seconds": 1.0, "keep_sound": True},
                    {"id": "A", "source": "SH01", "clip_in": 0, "seconds": 2.0, "keep_sound": True},
                ]
            },
        )
        self.assertEqual(
            [(s["id"], s["start"], s["duration"], s["clip"]) for s in out["shots"]],
            [("B", 0.0, 1.0, "b.mp4"), ("A", 1.0, 2.0, "a.mp4")],
        )
        self.assertEqual(out["size"], [720, 1280])

    def test_sounds_and_subtitles_inside_the_new_length_move_with_the_row(self):
        out = recut.recut(
            EDIT,
            {
                "rows": [
                    {"id": "B", "source": "SH02", "clip_in": 0.5, "seconds": 1.0, "keep_sound": True},
                    {"id": "A", "source": "SH01", "clip_in": 0, "seconds": 2.0, "keep_sound": True},
                ]
            },
        )
        self.assertEqual(
            [(s["path"], s["at"]) for s in out["sounds"]],
            [("audio/line2.wav", 0.2), ("audio/line1.wav", 1.5), ("audio/room-tone.wav", 1.0)],
        )
        self.assertEqual(
            [(s["text"], s["start"], s["end"]) for s in out["subtitles"]], [("two", 0.2, 1.0), ("one", 1.5, 2.5)]
        )

    def test_a_later_clip_in_moves_the_sound_window_with_the_picture(self):
        out = recut.recut(
            EDIT, {"rows": [{"id": "A", "source": "SH01", "clip_in": 3.0, "seconds": 1.0, "keep_sound": True}]}
        )
        self.assertEqual([(s["path"], s["at"]) for s in out["sounds"]], [("audio/door.wav", 0.5)])

    def test_keep_sound_false_drops_the_row_sounds_and_subtitles(self):
        out = recut.recut(
            EDIT, {"rows": [{"id": "A", "source": "SH01", "clip_in": 0, "seconds": 4.0, "keep_sound": False}]}
        )
        self.assertEqual((out["sounds"], out["subtitles"]), ([], []))

    def test_drop_patterns_extra_sounds_and_titles_come_from_the_rows_file(self):
        title = {"text": "New title", "start": 1.0, "end": 2.0}
        sting = {"path": "audio/sting.wav", "at": 0.0, "gain": 0.9}
        out = recut.recut(
            EDIT,
            {
                "rows": [{"id": "A", "source": "SH01", "clip_in": 0, "seconds": 4.0, "keep_sound": True}],
                "drop_sounds": ["room-tone"],
                "sounds": [sting],
                "titles": [title],
            },
        )
        self.assertEqual([s["path"] for s in out["sounds"]], ["audio/line1.wav", "audio/door.wav", "audio/sting.wav"])
        self.assertEqual(out["titles"], [title])

    def test_without_titles_in_the_rows_file_the_cut_has_none(self):
        out = recut.recut(
            EDIT, {"rows": [{"id": "A", "source": "SH01", "clip_in": 0, "seconds": 1.0, "keep_sound": True}]}
        )
        self.assertEqual(out["titles"], [])

    def test_unknown_source_shot_fails(self):
        with self.assertRaises(ValueError):
            recut.recut(
                EDIT, {"rows": [{"id": "A", "source": "SH99", "clip_in": 0, "seconds": 1.0, "keep_sound": True}]}
            )

    def test_cli_writes_the_cut(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "edit.json").write_text(json.dumps(EDIT))
            (root / "rows.json").write_text(
                json.dumps({"rows": [{"id": "A", "source": "SH01", "clip_in": 0, "seconds": 1.0, "keep_sound": True}]})
            )
            run = subprocess.run(
                [sys.executable, str(SCRIPT), str(root / "edit.json"), str(root / "rows.json"), str(root / "out.json")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads((root / "out.json").read_text())["shots"][0]["id"], "A")


if __name__ == "__main__":
    unittest.main()
