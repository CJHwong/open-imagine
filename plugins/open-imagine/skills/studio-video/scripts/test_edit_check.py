#!/usr/bin/env python3
"""Tests for edit_check.py, on short synthetic clips made with ffmpeg's lavfi sources."""

import itertools
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import edit_check


def make_clip(path, source, seconds):
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"{source}{':' if '=' in source else '='}size=96x160:rate=24:duration={seconds}",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


class EditCheckTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.scratch.name)

    def tearDown(self):
        self.scratch.cleanup()

    def shot(self, name, source, seconds, duration):
        make_clip(self.root / f"{name}.mp4", source, seconds)
        return {"id": name, "clip": f"{name}.mp4", "clip_in": 0, "duration": duration}

    def failed(self, findings, check):
        return [f for f in findings if f["check"] == check and f["result"] == "fail"]

    def test_real_footage_is_not_read_for_drawn_text(self):
        shots = [{"id": "SH01", "clip": "a.mp4"}, {"id": "F1", "clip": "b.mp4", "source": "footage"}]
        self.assertEqual([s["id"] for s in edit_check.text_shots(shots)], ["SH01"])

    def test_clip_shorter_than_its_slot_fails(self):
        shot = self.shot("SH01", "testsrc", 1.0, 2.0)
        self.assertTrue(self.failed(edit_check.check_clip(self.root, shot), "clip_length"))

    def test_clip_covering_its_slot_passes_length(self):
        shot = self.shot("SH01", "testsrc", 2.5, 2.0)
        self.assertFalse(self.failed(edit_check.check_clip(self.root, shot), "clip_length"))

    def test_black_frames_inside_the_slot_fail(self):
        shot = self.shot("SH01", "color=c=black", 2.0, 2.0)
        self.assertTrue(self.failed(edit_check.check_clip(self.root, shot), "black"))

    def test_moving_picture_has_no_black_or_freeze(self):
        shot = self.shot("SH01", "testsrc2", 2.5, 2.0)
        findings = edit_check.check_clip(self.root, shot)
        self.assertFalse(self.failed(findings, "black"))
        self.assertFalse(self.failed(findings, "freeze"))

    def test_still_picture_longer_than_a_second_is_a_freeze(self):
        shot = self.shot("SH01", "color=c=gray", 2.5, 2.0)
        self.assertTrue(self.failed(edit_check.check_clip(self.root, shot), "freeze"))

    def test_end_hold_measures_the_last_half_second(self):
        still = edit_check.check_clip(self.root, self.shot("SH01", "color=c=gray", 2.5, 2.0))
        moving = edit_check.check_clip(self.root, self.shot("SH02", "testsrc2", 2.5, 2.0))

        def hold(findings):
            return next(f["value"] for f in findings if f["check"] == "end_hold")

        self.assertLess(hold(still), 0.5)
        self.assertGreater(hold(moving), hold(still))

    def test_overlapping_subtitles_fail(self):
        subtitles = [{"text": "a", "start": 1.0, "end": 2.0}, {"text": "b", "start": 1.5, "end": 3.0}]
        self.assertTrue(self.failed(edit_check.check_subtitles(subtitles), "subtitle_overlap"))

    def test_back_to_back_subtitles_pass(self):
        subtitles = [{"text": "a", "start": 1.0, "end": 2.0}, {"text": "b", "start": 2.0, "end": 3.0}]
        self.assertFalse(self.failed(edit_check.check_subtitles(subtitles), "subtitle_overlap"))

    def test_text_in_a_shot_fails_unless_expected(self):
        readings = {"SH06": [("是吗", 0.5)], "SH14": [("鼎盛集团", 0.9)], "SH01": []}
        findings = edit_check.judge_text(readings, expected={"SH14"})
        self.assertEqual([f["shot"] for f in findings if f["result"] == "fail"], ["SH06"])

    def test_text_samples_cover_the_slot_with_no_gap_over_a_step(self):
        # A drawn caption showed at 1.0 s and 2.5 s and not at 1.75 s, so four samples missed it.
        times = edit_check.text_times({"clip_in": 0.5, "duration": 3.5}, length=4.04)
        slot = times[:-1]
        self.assertEqual(slot[0], 0.5)
        self.assertGreaterEqual(slot[-1], 0.5 + 3.5 - edit_check.TEXT_STEP)
        self.assertTrue(all(b - a <= edit_check.TEXT_STEP for a, b in itertools.pairwise(slot)))
        self.assertAlmostEqual(times[-1], 4.04 - 1.5 / edit_check.FPS)

    def test_text_samples_stop_at_the_end_of_a_short_clip(self):
        # A 1 s clip in a 3.5 s slot: ffmpeg writes no frame past the end, and OCR crashed on the missing file.
        times = edit_check.text_times({"clip_in": 0, "duration": 3.5}, length=1.0)
        self.assertTrue(all(at <= 1.0 - 1.5 / edit_check.FPS for at in times))

    def test_text_accepted_after_review_passes_and_says_so(self):
        readings = {"SH06": [("2m", 0.3)], "SH12": [("2m", 0.3)]}
        findings = edit_check.judge_text(readings, expected=set(), accepted={("SH06", "2m")})
        self.assertEqual([f["shot"] for f in findings if f["result"] == "fail"], ["SH12"])
        self.assertIn("accepted", next(f["evidence"] for f in findings if f["shot"] == "SH06"))

    def test_export_without_audio_or_wrong_length_fails(self):
        make_clip(self.root / "film.mp4", "testsrc", 2.0)
        findings = edit_check.check_export(self.root / "film.mp4", 3.0)
        self.assertTrue(self.failed(findings, "export_length"))
        self.assertTrue(self.failed(findings, "export_audio"))

    def test_command_writes_a_report_and_exits_nonzero_on_a_fail(self):
        shot = self.shot("SH01", "testsrc", 1.0, 2.0)
        (self.root / "edit.json").write_text(json.dumps({"shots": [{**shot, "start": 0}], "subtitles": []}))
        run = subprocess.run(
            [sys.executable, str(pathlib.Path(edit_check.__file__)), str(self.root / "edit.json")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 1)
        self.assertFalse(json.loads(run.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
