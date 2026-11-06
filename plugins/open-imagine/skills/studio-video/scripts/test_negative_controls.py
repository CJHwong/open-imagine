#!/usr/bin/env python3
"""Tests for negative_controls.py, on short synthetic clips made with ffmpeg's lavfi sources."""

import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import edit_check
import negative_controls


def make_clip(path, seconds, rate=24, size="360x640", audio=False):
    sources = ["-f", "lavfi", "-i", f"testsrc=size={size}:rate={rate}:duration={seconds}"]
    if audio:
        sources += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *sources, "-pix_fmt", "yuv420p", "-shortest", str(path)], check=True)


class NegativeControlsTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.scratch.name)
        make_clip(self.root / "SH01.mp4", 3.0)
        self.shot = {"id": "SH01", "start": 0, "duration": 3.0, "clip": "SH01.mp4", "clip_in": 0}

    def tearDown(self):
        self.scratch.cleanup()

    def failed_after(self, fault, clip="SH01.mp4"):
        planted = self.root / f"{fault}.mp4"
        negative_controls.plant(fault, self.root / clip, planted, 1.5, self.root)
        edit = {"shots": [dict(self.shot, clip=str(planted))], "subtitles": []}
        return negative_controls.run_edit_check(edit, self.root)

    def test_each_planted_clip_fault_fails_only_its_own_check(self):
        for fault in ("black", "freeze", "clip_length"):
            with self.subTest(fault=fault):
                self.assertEqual(self.failed_after(fault), [fault])

    def test_freeze_follows_the_clip_frame_rate(self):
        make_clip(self.root / "fast.mp4", 3.0, rate=30)
        self.assertEqual(self.failed_after("freeze", "fast.mp4"), ["freeze"])
        length, _ = edit_check.probe(self.root / "freeze.mp4")
        self.assertAlmostEqual(length, 3.0, delta=0.1)

    def test_clean_clip_fails_nothing(self):
        edit = {"shots": [self.shot | {"clip": str(self.root / "SH01.mp4")}], "subtitles": []}
        self.assertEqual(negative_controls.run_edit_check(edit, self.root), [])

    def test_without_vision_the_text_control_is_skipped_not_passed(self):
        with mock.patch.object(negative_controls, "vision_available", return_value=False):
            results = negative_controls.clip_controls(self.shot, self.root, self.root, negative_controls.CAPTION, None)
        self.assertIn(("drawn_text", ["drawn_text"], None), results)
        with redirect_stdout(io.StringIO()) as out:
            behaved, skipped = negative_controls.report(results)
        self.assertEqual((behaved, skipped), (len(results) - 1, 1))
        self.assertIn("1 skipped", out.getvalue())

    def test_a_wrong_result_is_counted_as_misbehaving(self):
        with redirect_stdout(io.StringIO()) as out:
            behaved, skipped = negative_controls.report([("black", ["black"], []), ("freeze", ["freeze"], ["freeze"])])
        self.assertEqual((behaved, skipped), (1, 0))
        self.assertIn("WRONG", out.getvalue())

    @unittest.skipUnless(negative_controls.vision_available(), "needs macOS Vision through uv")
    def test_a_short_drawn_caption_fails_the_text_check(self):
        planted = self.root / "drawn_text.mp4"
        negative_controls.plant("drawn_text", self.root / "SH01.mp4", planted, 1.5, self.root)
        edit = {"shots": [dict(self.shot, clip=str(planted))], "subtitles": []}
        self.assertEqual(negative_controls.run_edit_check(edit, self.root, "--text"), ["drawn_text"])

    def test_export_controls_each_fail_only_their_own_check(self):
        make_clip(self.root / "film.mp4", 3.0, audio=True)
        edit = {"shots": [self.shot], "subtitles": []}
        results = negative_controls.export_controls(edit, self.root, self.root / "film.mp4", self.root)
        self.assertEqual(
            [(name, expected) for name, expected, _ in results],
            [
                ("none (clean export)", []),
                ("export_length", ["export_length"]),
                ("export_audio", ["export_audio"]),
                ("export_peak", ["export_peak"]),
            ],
        )
        for name, expected, failed in results:
            with self.subTest(control=name):
                self.assertEqual(failed, expected)


if __name__ == "__main__":
    unittest.main()
