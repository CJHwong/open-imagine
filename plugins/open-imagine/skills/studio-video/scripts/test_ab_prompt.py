#!/usr/bin/env python3
"""Tests for ab_prompt.py: same-seed prompt A/B pairs that differ only in the prompt."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ab_prompt

SCRIPT = pathlib.Path(__file__).resolve().parent / "ab_prompt.py"

BASE = {
    "name": "SH03-G40",
    "out": "../storyboard/ab/SH03-G40.png",
    "references": ["../assets/A.png", "../storyboard/SH03.png"],
    "request": {"kind": "image", "mode": "edit", "seed": 1, "prompt": "Keep Image 2 exactly."},
    "b_prompt": "Image 2 is the frame. Preserve its camera.",
}


class AbPromptTest(unittest.TestCase):
    def test_each_seed_gives_an_a_and_a_b_job_in_order(self):
        jobs = ab_prompt.pairs([BASE], [9701, 9702])
        self.assertEqual(
            [j["name"] for j in jobs], ["SH03-G40-A9701", "SH03-G40-B9701", "SH03-G40-A9702", "SH03-G40-B9702"]
        )
        self.assertEqual(jobs[1]["out"], "../storyboard/ab/SH03-G40-B9701.png")

    def test_both_arms_share_the_seed_and_keep_its_type(self):
        a, b = ab_prompt.pairs([BASE], [9701])
        self.assertEqual((a["request"]["seed"], b["request"]["seed"]), (9701, 9701))
        text_seed = dict(BASE, request=dict(BASE["request"], seed="1"))
        self.assertEqual(ab_prompt.pairs([text_seed], [9701])[0]["request"]["seed"], "9701")

    def test_only_the_prompt_differs_between_the_arms(self):
        a, b = ab_prompt.pairs([BASE], [9701])
        self.assertEqual(a["request"]["prompt"], BASE["request"]["prompt"])
        self.assertEqual(b["request"]["prompt"], BASE["b_prompt"])
        self.assertNotIn("b_prompt", a)
        self.assertNotIn("b_prompt", b)
        self.assertEqual(a["references"], b["references"])

    def test_a_job_without_a_b_prompt_fails(self):
        with self.assertRaisesRegex(ValueError, "b_prompt"):
            ab_prompt.pairs([{k: v for k, v in BASE.items() if k != "b_prompt"}], [1])

    def test_a_b_prompt_equal_to_a_fails(self):
        with self.assertRaisesRegex(ValueError, "same"):
            ab_prompt.pairs([dict(BASE, b_prompt=BASE["request"]["prompt"])], [1])

    def test_check_pair_refuses_any_other_difference(self):
        a, b = ab_prompt.pairs([BASE], [9701])
        b["references"] = b["references"][:1]
        with self.assertRaisesRegex(ValueError, "references"):
            ab_prompt.check_pair(a, b)

    def test_cli_writes_the_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            (root / "base.json").write_text(json.dumps([BASE]))
            run = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(root / "base.json"),
                    "--seeds",
                    "5",
                    "6",
                    "--out",
                    str(root / "queue.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(len(json.loads((root / "queue.json").read_text())), 4)


if __name__ == "__main__":
    unittest.main()
