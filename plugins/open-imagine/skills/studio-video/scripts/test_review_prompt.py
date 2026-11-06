#!/usr/bin/env python3
"""Tests for the review page's Copy prompt builder, run in node as the pure function the page uses."""

import json
import pathlib
import shutil
import subprocess
import unittest

PAGE = (pathlib.Path(__file__).resolve().parent.parent / "assets" / "review.html").read_text()
START, END = "// prompt-builder:start", "// prompt-builder:end"

PROJECT = {
    "id": "test-film",
    "revision": 7,
    "title": "The Bus",
    "production": {"storyboard_version": "kf4"},
    "shots": [
        {
            "id": "SH01",
            "purpose": "Setup",
            "selected": "v001",
            "versions": [
                {"id": "v001", "storyboard_image": "storyboard/SH01.png", "video": "shots/SH01/v001/clip.mp4"}
            ],
        },
        {
            "id": "SH02",
            "title": "The miss",
            "purpose": "Miss",
            "selected": "v001",
            "versions": [
                {"id": "v001", "storyboard_image": "storyboard/SH02-a.png"},
                {
                    "id": "v002",
                    "storyboard_image": "storyboard/SH02-b.png",
                    "generation": [
                        {
                            "step": "Stage 1",
                            "backend": "qwen21_turbo",
                            "mode": "generate",
                            "seed": 9801,
                            "settings": {"strength": 0.3, "size": "720x1280"},
                            "prompt": "long prompt text",
                        }
                    ],
                },
            ],
        },
        {
            "id": "SH03",
            "purpose": "Untouched",
            "selected": "v001",
            "versions": [{"id": "v001", "storyboard_image": "storyboard/SH03.png"}],
        },
    ],
    "assets": [
        {
            "id": "LEAD",
            "kind": "character",
            "label": "Maya",
            "selected": "v001",
            "versions": [{"id": "v001", "image": "assets/LEAD.png"}],
        },
    ],
}


def draft(**changes):
    base = {
        n["id"]: {
            "id": n["id"],
            "base_selected": n["selected"],
            "selected": n["selected"],
            "review_status": "unreviewed",
            "notes": "",
            "takes": {},
        }
        for n in PROJECT["shots"] + PROJECT["assets"]
    }
    for node_id, change in changes.items():
        base[node_id].update(change)
    return base


@unittest.skipUnless(shutil.which("node"), "needs node to run the page's builder")
class PromptBuilderTest(unittest.TestCase):
    def build(self, drafts, mode="storyboard"):
        builder = PAGE[PAGE.index(START) : PAGE.index(END)]
        script = f"{builder}\nprocess.stdout.write(JSON.stringify(buildPrompt({json.dumps(PROJECT)}, {json.dumps(drafts)}, {json.dumps(mode)})));"
        run = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
        return json.loads(run.stdout)

    def test_nothing_touched_gives_no_prompt(self):
        self.assertIsNone(self.build(draft()))

    def test_header_names_project_revision_mode_and_storyboard_version(self):
        text = self.build(draft(SH01={"notes": "Too dark."}))
        for expected in ("The Bus", "test-film", "r7", "storyboard", "kf4"):
            self.assertIn(expected, text.split("\n## ")[0])

    def test_only_touched_items_appear_in_shot_then_asset_order(self):
        text = self.build(
            draft(LEAD={"review_status": "approved"}, SH02={"notes": "x"}, SH01={"review_status": "revise"})
        )
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["## SH01: Setup", "## SH02: The miss", "## LEAD: Maya"])

    def test_decision_take_path_and_generation_settings(self):
        text = self.build(draft(SH02={"selected": "v002", "review_status": "revise", "notes": "Lattice changed."}))
        section = text.split("## SH02")[1]
        self.assertIn("Decision: Revise", section)
        self.assertIn("Take: v002 (`storyboard/SH02-b.png`)", section)
        self.assertIn("Base take: v001", section)
        self.assertIn("Stage 1: qwen21_turbo, generate, seed 9801, strength 0.3, size 720x1280", section)
        self.assertNotIn("long prompt text", section)

    def test_an_absent_or_null_seed_is_omitted(self):
        PROJECT["shots"][1]["versions"][1]["generation"].append({"step": "Paste", "mode": "composite", "seed": None})
        try:
            text = self.build(draft(SH02={"selected": "v002"}))
        finally:
            PROJECT["shots"][1]["versions"][1]["generation"].pop()
        self.assertIn("Paste: composite", text)
        self.assertNotIn("seed null", text)

    def test_shots_mode_names_the_clip(self):
        text = self.build(draft(SH01={"review_status": "approved"}), mode="shots")
        self.assertIn("Decision: Keep", text)
        self.assertIn("`shots/SH01/v001/clip.mp4`", text)

    def test_the_note_is_verbatim_and_its_playhead_times_are_listed(self):
        note = "[edit 00:12.5] the bow comes late\n[SH01 source 00:01.2] hand <jumps> & *flickers*"
        text = self.build(draft(SH01={"notes": note}))
        self.assertIn(note, text)
        self.assertIn("Playhead times: edit 00:12.5, SH01 source 00:01.2", text)

    def test_per_take_decisions_are_listed(self):
        takes = {"v001": {"review_status": "revise", "notes": "wrong hand"}}
        text = self.build(draft(SH02={"selected": "v002", "takes": takes}))
        self.assertIn("- v001: Revise. wrong hand", text)

    def test_a_status_or_note_already_in_the_manifest_is_not_a_touch(self):
        """Drafts start from the manifest's own status and notes; only what the user changes on the page counts."""
        global PROJECT
        saved = PROJECT
        PROJECT = json.loads(json.dumps(saved))
        try:
            PROJECT["assets"][0]["versions"][0].update(review_status="selected by agent", notes="imported earlier")
            self.assertIsNone(
                self.build(draft(LEAD={"review_status": "selected by agent", "notes": "imported earlier"}))
            )
            text = self.build(draft(LEAD={"review_status": "approved", "notes": "imported earlier"}))
            self.assertIn("Decision: Keep", text)
        finally:
            PROJECT = saved

    def test_an_unchanged_take_shows_no_base_take(self):
        text = self.build(draft(SH01={"notes": "ok"}))
        self.assertNotIn("Base take", text)
        self.assertNotIn("How it was made", text)


if __name__ == "__main__":
    unittest.main()
