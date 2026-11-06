#!/usr/bin/env python3
"""Tests for blind_ab.py: blind frame-sheet packets for two cuts, and the verdict import."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from typing import ClassVar

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import blind_ab

SCRIPT = pathlib.Path(__file__).resolve().parent / "blind_ab.py"


def make_film(path, seconds, source="testsrc"):
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"{source}=size=180x320:rate=24:duration={seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=duration={seconds}",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            str(path),
        ],
        check=True,
    )


def make_edit(path, seconds):
    path.write_text(
        json.dumps(
            {
                "shots": [
                    {"id": "SH01", "start": 0, "duration": seconds / 2},
                    {"id": "SH02", "start": seconds / 2, "duration": seconds / 2},
                ],
                "subtitles": [{"text": "hello", "start": 0.5, "end": 1.5}],
                "titles": [{"text": "Title", "start": 0, "end": 1}],
                "sounds": [{"path": "audio/takes/L1.wav", "at": 0.2}],
            }
        )
    )


class SidesTest(unittest.TestCase):
    def test_same_seed_gives_same_sides(self):
        self.assertEqual(blind_ab.sides(7, "aa", "bb"), blind_ab.sides(7, "aa", "bb"))

    def test_some_seed_swaps_the_sides(self):
        self.assertEqual({blind_ab.sides(seed, "aa", "bb") for seed in range(20)}, {("X", "Y"), ("Y", "X")})


class LabelTest(unittest.TestCase):
    def test_the_time_label_is_drawn_inside_its_frame(self):
        from PIL import Image

        frame = Image.new("RGB", (120, 200), "white")
        box = blind_ab.label(frame, "12.5s")
        left, top, right, bottom = box
        self.assertTrue(0 <= left < right <= 120 and 0 <= top < bottom <= 200)
        self.assertNotEqual(frame.getpixel((left + 1, top + 1)), (255, 255, 255))


class PackTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.scratch.name)
        make_film(self.root / "a.mp4", 2.0)
        make_film(self.root / "b.mp4", 3.0, "testsrc2")
        make_edit(self.root / "a.json", 2.0)
        make_edit(self.root / "b.json", 3.0)

    def tearDown(self):
        self.scratch.cleanup()

    def pack(self, seed=1, name="packet"):
        return blind_ab.pack(
            self.root / "a.mp4",
            self.root / "a.json",
            "cutA",
            self.root / "b.mp4",
            self.root / "b.json",
            "cutB",
            seed,
            self.root / name,
            step=0.5,
        )

    def test_pack_writes_a_sheet_and_text_per_side_and_keeps_the_key_outside(self):
        key_path = self.pack()
        packet = self.root / "packet"
        self.assertEqual(
            sorted(p.name for p in packet.iterdir()), ["README.txt", "cut-X.png", "cut-X.txt", "cut-Y.png", "cut-Y.txt"]
        )
        self.assertNotEqual(key_path.parent, packet)
        key = json.loads(key_path.read_text())
        self.assertEqual(sorted(key["sides"].values()), ["cutA", "cutB"])
        self.assertNotIn("cutA", "".join(p.read_text() for p in packet.glob("*.txt")))

    def test_the_text_lists_cuts_subtitles_titles_and_sounds(self):
        key = json.loads(self.pack().read_text())
        side = next(s for s, label in key["sides"].items() if label == "cutB")
        text = (self.root / "packet" / f"cut-{side}.txt").read_text()
        for expected in ("length 3.0 s", "cuts at: 0.0, 1.5", "0.5-1.5 s  hello", "0.0-1.0 s  Title", "0.2 s  L1"):
            self.assertIn(expected, text)

    def test_the_readme_says_what_frame_sheets_cannot_judge(self):
        self.pack()
        readme = (self.root / "packet" / "README.txt").read_text().lower()
        for limit in ("sound", "motion", "lip sync", "pacing"):
            self.assertIn(limit, readme)

    def test_same_seed_gives_the_same_packet(self):
        first, second = self.pack(3, "one"), self.pack(3, "two")
        self.assertEqual(json.loads(first.read_text())["sides"], json.loads(second.read_text())["sides"])
        self.assertEqual((self.root / "one" / "cut-X.png").read_bytes(), (self.root / "two" / "cut-X.png").read_bytes())

    def test_pack_refuses_a_folder_that_holds_files(self):
        (self.root / "busy").mkdir()
        (self.root / "busy" / "old.txt").write_text("x")
        with self.assertRaises(ValueError):
            self.pack(name="busy")


class VerdictsTest(unittest.TestCase):
    KEY: ClassVar[dict] = {"sides": {"X": "r80", "Y": "tension"}, "lengths": {"X": 60.0, "Y": 32.0}}

    def verdict(self, **changes):
        base = {
            "prefer": "Y",
            "reason": "the hook lands sooner",
            "findings": [{"side": "Y", "frames": [0.0, 2.0], "observation": "the bow opens the film"}],
        }
        return base | changes

    def test_tally_unblinds_each_choice(self):
        result = blind_ab.tally(self.KEY, {"r1": self.verdict(), "r2": self.verdict(), "r3": self.verdict(prefer="X")})
        self.assertEqual(result["preferred"], {"tension": 2, "r80": 1})
        self.assertEqual(result["reviewers"]["r3"]["prefer"], "r80")
        self.assertEqual(result["reviewers"]["r1"]["findings"][0]["cut"], "tension")

    def test_a_finding_without_a_frame_range_is_rejected(self):
        bad = self.verdict(findings=[{"side": "Y", "observation": "slow"}])
        with self.assertRaisesRegex(ValueError, "frame range"):
            blind_ab.tally(self.KEY, {"r1": bad})

    def test_a_range_outside_the_cut_is_rejected(self):
        bad = self.verdict(findings=[{"side": "Y", "frames": [30.0, 40.0], "observation": "late"}])
        with self.assertRaisesRegex(ValueError, "outside"):
            blind_ab.tally(self.KEY, {"r1": bad})

    def test_an_unknown_choice_is_rejected(self):
        with self.assertRaises(ValueError):
            blind_ab.tally(self.KEY, {"r1": self.verdict(prefer="Z")})

    def test_no_preference_is_allowed(self):
        self.assertEqual(blind_ab.tally(self.KEY, {"r1": self.verdict(prefer="none")})["preferred"], {"none": 1})


class CliTest(unittest.TestCase):
    def test_verdicts_command_prints_the_tally(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "key.json").write_text(json.dumps(VerdictsTest.KEY))
            (root / "r1.json").write_text(json.dumps(VerdictsTest().verdict()))
            run = subprocess.run(
                [sys.executable, str(SCRIPT), "verdicts", str(root / "key.json"), str(root / "r1.json")],
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["preferred"], {"tension": 1})


if __name__ == "__main__":
    unittest.main()
