#!/usr/bin/env python3
"""Tests for the storyboard readiness and approval gates in review.py."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import review

SCRIPT = pathlib.Path(__file__).resolve().parent / "review.py"

PASSING_FINDING = {
    "relationship": "Phone stays in her right hand",
    "shots": ["SH01", "SH02"],
    "result": "pass",
    "evidence": "Right hand holds the phone in both frames.",
}
PASSING_VERDICT = {
    "verdict": "pass",
    "tell_back": "She rides the bus and watches her phone.",
    "findings": [PASSING_FINDING],
}

BLOCKING_FINDING = {**PASSING_FINDING, "result": "fail", "severity": "block"}
REVISE_FINDING = {
    "relationship": "Lattice pattern matches across cameras",
    "shots": ["SH02"],
    "result": "fail",
    "severity": "revise",
    "evidence": "SH02 shows a coarser lattice than SH01.",
}

FAILING_VERDICT = {
    "verdict": "fail",
    "tell_back": "She rides the bus and watches her phone.",
    "findings": [BLOCKING_FINDING],
}


CARD = {
    "mover": "her right hand lifts the phone",
    "camera_move": "locked",
    "mouth_visible": "hidden",
    "end_state": "phone at her ear",
}


def make_project(root):
    for name in ["map.png", "SH01.png", "SH02.png"]:
        (root / name).write_bytes(name.encode())
    project = {
        "schema_version": 1,
        "id": "test-film",
        "revision": 1,
        "title": "Test",
        "brief": "",
        "settings": {"target_seconds": 8, "max_shot_seconds": 6},
        "staging": {
            "map": "map.png",
            "cameras": ["C1", "C2"],
            "timeline": [{"id": "T1", "state": "Bus departs"}, {"id": "T2", "state": "Stop passes"}],
        },
        "assets": [],
        "shots": [
            {
                "id": "SH01",
                "start": 0,
                "duration": 4,
                "purpose": "Setup",
                "selected": "v001",
                "staging": {"camera": "C1", "world_time": "T1", **CARD},
                "versions": [{"id": "v001", "storyboard_image": "SH01.png"}],
            },
            {
                "id": "SH02",
                "start": 4,
                "duration": 4,
                "purpose": "Miss",
                "selected": "v001",
                "staging": {"camera": "C2", "world_time": "T2", **CARD},
                "versions": [{"id": "v001", "storyboard_image": "SH02.png"}],
            },
        ],
        "history": [],
    }
    path = root / "project.json"
    path.write_text(json.dumps(project))
    return project, path


PASSING_CHECK = {"verdict": "pass", "findings": [PASSING_FINDING]}


def add_cast(project, root):
    (root / "LEAD.png").write_bytes(b"front")
    (root / "LEAD-back.png").write_bytes(b"back")
    project["assets"].append(
        {
            "id": "LEAD",
            "kind": "character",
            "selected": "v001",
            "versions": [
                {"id": "v001", "image": "LEAD.png", "reference_views": [{"view": "back", "image": "LEAD-back.png"}]}
            ],
        }
    )


def add_line(project, root, direction="[flat, tired] I missed it."):
    (root / "L1.wav").write_bytes(b"line")
    (root / "door.wav").write_bytes(b"bang")
    project["shots"][1]["dialogue"] = [
        {"speaker": "LEAD", "line": "I missed it.", "audio": "L1.wav", "direction": direction, "at": 0.5}
    ]
    project["shots"][1]["sound_files"] = ["door.wav"]


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.project, self.path = make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def reviewed_and_approved(self):
        reviewed = review.record_verdict(self.project, self.path, PASSING_VERDICT)
        return review.approve(reviewed, self.path, "Approved storyboard v003, go ahead.")

    def test_missing_staging_map_blocks_readiness(self):
        del self.project["staging"]
        problems = review.readiness(self.project, self.path)
        self.assertTrue(any("staging" in p for p in problems))

    def test_shot_citing_unknown_camera_blocks_readiness(self):
        self.project["shots"][1]["staging"]["camera"] = "C9"
        problems = review.readiness(self.project, self.path)
        self.assertTrue(any("SH02" in p and "camera" in p for p in problems))

    def test_shot_citing_unknown_world_time_blocks_readiness(self):
        del self.project["shots"][0]["staging"]["world_time"]
        problems = review.readiness(self.project, self.path)
        self.assertTrue(any("SH01" in p and "world_time" in p for p in problems))

    def test_board_without_blind_review_is_not_ready(self):
        problems = review.readiness(self.project, self.path)
        self.assertTrue(any("blind" in p for p in problems))

    def test_passing_blind_review_makes_board_ready(self):
        reviewed = review.record_verdict(self.project, self.path, PASSING_VERDICT)
        self.assertEqual(review.readiness(reviewed, self.path), [])

    def test_failing_blind_review_keeps_board_not_ready(self):
        failing = {"verdict": "fail", "tell_back": "Lost at SH02.", "findings": [BLOCKING_FINDING]}
        reviewed = review.record_verdict(self.project, self.path, failing)
        problems = review.readiness(reviewed, self.path)
        self.assertTrue(any("failed" in p for p in problems))

    def test_pass_verdict_with_a_blocking_finding_is_rejected(self):
        contradictory = {"verdict": "pass", "tell_back": "Reads.", "findings": [BLOCKING_FINDING]}
        with self.assertRaises(ValueError):
            review.record_verdict(self.project, self.path, contradictory)

    def test_verdict_without_findings_is_rejected(self):
        with self.assertRaises(ValueError):
            review.record_verdict(self.project, self.path, {"verdict": "pass", "findings": []})

    def test_verdict_without_tell_back_is_rejected(self):
        without = {k: v for k, v in PASSING_VERDICT.items() if k != "tell_back"}
        with self.assertRaises(ValueError):
            review.record_verdict(self.project, self.path, without)

    def test_tell_back_is_recorded(self):
        reviewed = review.record_verdict(self.project, self.path, PASSING_VERDICT)
        self.assertEqual(reviewed["storyboard_review"]["tell_back"], PASSING_VERDICT["tell_back"])

    def test_changed_frame_after_review_blocks_readiness(self):
        reviewed = review.record_verdict(self.project, self.path, PASSING_VERDICT)
        (self.root / "SH02.png").write_bytes(b"repainted")
        problems = review.readiness(reviewed, self.path)
        self.assertTrue(any("SH02" in p for p in problems))

    def test_gate_refuses_without_approval(self):
        reviewed = review.record_verdict(self.project, self.path, PASSING_VERDICT)
        problems = review.gate(reviewed, self.path, None)
        self.assertTrue(any("approv" in p for p in problems))

    def test_approval_requires_a_ready_board(self):
        with self.assertRaises(ValueError):
            review.approve(self.project, self.path, "Looks good")

    def test_approval_requires_the_producer_words(self):
        reviewed = review.record_verdict(self.project, self.path, PASSING_VERDICT)
        with self.assertRaises(ValueError):
            review.approve(reviewed, self.path, "  ")

    def test_gate_passes_after_review_and_approval(self):
        approved = self.reviewed_and_approved()
        self.assertEqual(review.gate(approved, self.path, None), [])
        self.assertEqual(approved["history"][-1]["user_words"], "Approved storyboard v003, go ahead.")

    def test_changed_shot_blocks_only_its_own_submission(self):
        approved = self.reviewed_and_approved()
        approved["shots"][1]["purpose"] = "A different beat"
        self.assertEqual(review.gate(approved, self.path, ["SH01"]), [])
        self.assertTrue(review.gate(approved, self.path, ["SH02"]))

    def test_changed_staging_map_blocks_every_shot(self):
        approved = self.reviewed_and_approved()
        (self.root / "map.png").write_bytes(b"moved the pole")
        self.assertTrue(review.gate(approved, self.path, ["SH01"]))

    def test_approval_refuses_a_failed_review_without_a_waiver(self):
        reviewed = review.record_verdict(self.project, self.path, FAILING_VERDICT)
        with self.assertRaises(ValueError):
            review.approve(reviewed, self.path, "Looks good")

    def test_waiver_opens_the_gate_and_records_the_failed_review(self):
        reviewed = review.record_verdict(self.project, self.path, FAILING_VERDICT)
        approved = review.approve(reviewed, self.path, "looks good. proceed generation.", waive_review=True)
        self.assertEqual(review.gate(approved, self.path, None), [])
        waived = approved["storyboard_approval"]["waived_review"]
        self.assertEqual(waived["at"], reviewed["storyboard_review"]["at"])
        self.assertEqual(waived["failed"], 1)

    def test_waiver_does_not_cover_a_later_review(self):
        reviewed = review.record_verdict(self.project, self.path, FAILING_VERDICT)
        approved = review.approve(reviewed, self.path, "go", waive_review=True)
        approved["storyboard_review"]["at"] = "a later review"
        self.assertTrue(review.gate(approved, self.path, None))

    def test_waiver_does_not_cover_a_changed_shot(self):
        reviewed = review.record_verdict(self.project, self.path, FAILING_VERDICT)
        approved = review.approve(reviewed, self.path, "go", waive_review=True)
        approved["shots"][1]["purpose"] = "A different beat"
        self.assertTrue(review.gate(approved, self.path, ["SH02"]))

    def test_waiver_needs_a_failed_review(self):
        reviewed = review.record_verdict(self.project, self.path, PASSING_VERDICT)
        with self.assertRaises(ValueError):
            review.approve(reviewed, self.path, "go", waive_review=True)

    def test_gate_rejects_unknown_shot(self):
        approved = self.reviewed_and_approved()
        with self.assertRaises(ValueError):
            review.gate(approved, self.path, ["SH99"])

    def test_note_keeps_user_words_beside_interpretation(self):
        noted = review.note(self.project, "the train looks stationary", "Exterior lacks parallax after SH06")
        entry = noted["history"][-1]
        self.assertEqual(entry["user_words"], "the train looks stationary")
        self.assertEqual(entry["interpretation"], "Exterior lacks parallax after SH06")
        self.assertEqual(noted["revision"], 2)

    def test_input_given_as_a_bare_path_is_a_validation_error(self):
        self.project["shots"][0]["versions"][0]["inputs"] = ["assets/source.png"]
        with self.assertRaisesRegex(ValueError, "asset_id or shot_id"):
            review.validate(self.project)

    def test_gate_command_exits_nonzero_when_blocked(self):
        run = subprocess.run([sys.executable, str(SCRIPT), "gate", str(self.path)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertFalse(json.loads(run.stdout)["ok"])

    def test_gate_command_exits_zero_when_approved(self):
        self.path.write_text(json.dumps(self.reviewed_and_approved()))
        run = subprocess.run(
            [sys.executable, str(SCRIPT), "gate", str(self.path), "--shots", "SH01"], capture_output=True, text=True
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


class SeverityTest(unittest.TestCase):
    """A failed board finding is BLOCK or REVISE; only BLOCK keeps the board from the producer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.project, self.path = make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def verdict(self, verdict, *findings):
        return {
            "verdict": verdict,
            "tell_back": "She rides the bus and watches her phone.",
            "findings": [PASSING_FINDING, *findings],
        }

    def test_revise_findings_alone_leave_the_board_ready_and_listed(self):
        reviewed = review.record_verdict(self.project, self.path, self.verdict("pass", REVISE_FINDING))
        self.assertEqual(review.readiness(reviewed, self.path), [])
        self.assertEqual(review.open_revisions(reviewed), [REVISE_FINDING])

    def test_one_blocking_finding_keeps_the_board_not_ready(self):
        reviewed = review.record_verdict(
            self.project, self.path, self.verdict("fail", REVISE_FINDING, BLOCKING_FINDING)
        )
        self.assertTrue(any("failed" in p for p in review.readiness(reviewed, self.path)))

    def test_a_fail_verdict_needs_a_blocking_finding(self):
        with self.assertRaisesRegex(ValueError, "block"):
            review.record_verdict(self.project, self.path, self.verdict("fail", REVISE_FINDING))

    def test_a_new_failed_finding_needs_a_severity(self):
        unrated = {k: v for k, v in BLOCKING_FINDING.items() if k != "severity"}
        with self.assertRaisesRegex(ValueError, "severity"):
            review.record_verdict(self.project, self.path, self.verdict("fail", unrated))

    def test_an_unknown_severity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "severity"):
            review.record_verdict(
                self.project, self.path, self.verdict("fail", {**BLOCKING_FINDING, "severity": "minor"})
            )

    def test_a_stored_old_failed_review_without_severity_still_blocks(self):
        reviewed = review.record_verdict(self.project, self.path, PASSING_VERDICT)
        reviewed["storyboard_review"]["verdict"] = "fail"
        reviewed["storyboard_review"]["findings"] = [{**PASSING_FINDING, "result": "fail"}]
        self.assertTrue(any("failed" in p for p in review.readiness(reviewed, self.path)))
        self.assertEqual(review.open_revisions(reviewed), [])

    def test_casts_and_sound_checks_need_no_severity(self):
        add_cast(self.project, self.root)
        failing = {"verdict": "fail", "findings": [{**PASSING_FINDING, "result": "fail"}]}
        checked = review.record_check(self.project, self.path, "cast", failing)
        self.assertEqual(checked["checks"]["cast"]["verdict"], "fail")

    def test_approval_records_the_revise_findings_the_producer_saw(self):
        reviewed = review.record_verdict(self.project, self.path, self.verdict("pass", REVISE_FINDING))
        approved = review.approve(reviewed, self.path, "Approved, fix the lattice later.")
        self.assertEqual(approved["storyboard_approval"]["revise"], [REVISE_FINDING])

    def test_ready_command_lists_revise_findings_and_exits_zero(self):
        reviewed = review.record_verdict(self.project, self.path, self.verdict("pass", REVISE_FINDING))
        self.path.write_text(json.dumps(reviewed))
        run = subprocess.run([sys.executable, str(SCRIPT), "ready", str(self.path)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        report = json.loads(run.stdout)
        self.assertEqual(report["revise"], [REVISE_FINDING])


class CardLintTest(unittest.TestCase):
    """A layout card names what the reviewer checks against the frame; a card missing a field cannot be reviewed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.project, self.path = make_project(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_cards_pass(self):
        self.assertEqual(review.card_problems(self.project), [])

    def test_each_missing_field_is_named_with_its_shot(self):
        for field in ("camera", "world_time", "mover", "camera_move", "mouth_visible", "end_state"):
            with self.subTest(field=field):
                project = json.loads(json.dumps(self.project))
                del project["shots"][1]["staging"][field]
                problems = review.card_problems(project)
                self.assertTrue(any("SH02" in p and field in p for p in problems), problems)

    def test_a_blank_field_counts_as_missing(self):
        self.project["shots"][0]["staging"]["end_state"] = "  "
        self.assertTrue(any("SH01" in p and "end_state" in p for p in review.card_problems(self.project)))

    def test_mouth_visible_takes_only_the_three_values(self):
        self.project["shots"][0]["staging"]["mouth_visible"] = "partly"
        self.assertTrue(any("mouth_visible" in p for p in review.card_problems(self.project)))

    def test_a_shot_without_a_card_is_named(self):
        del self.project["shots"][0]["staging"]
        self.assertTrue(any("SH01" in p for p in review.card_problems(self.project)))

    def test_a_board_with_an_incomplete_card_cannot_be_reviewed(self):
        del self.project["shots"][0]["staging"]["end_state"]
        with self.assertRaisesRegex(ValueError, "end_state"):
            review.record_verdict(self.project, self.path, PASSING_VERDICT)

    def test_ready_and_gate_ignore_the_card_lint_for_an_approved_board(self):
        approved = review.approve(
            review.record_verdict(self.project, self.path, PASSING_VERDICT), self.path, "Approved."
        )
        for shot in approved["shots"]:
            shot["staging"] = {"camera": shot["staging"]["camera"], "world_time": shot["staging"]["world_time"]}
        approved["storyboard_review"]["shots"] = review.shot_digests(approved, self.path)
        approved["storyboard_approval"]["shots"] = review.shot_digests(approved, self.path)
        self.assertEqual(review.readiness(approved, self.path), [])
        self.assertEqual(review.gate(approved, self.path, None), [])

    def test_lint_command_exits_nonzero_and_names_the_gap(self):
        del self.project["shots"][1]["staging"]["mover"]
        self.path.write_text(json.dumps(self.project))
        run = subprocess.run([sys.executable, str(SCRIPT), "lint", str(self.path)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertTrue(any("SH02" in p and "mover" in p for p in json.loads(run.stdout)["problems"]))


class ApprovalBindingTest(unittest.TestCase):
    """A waiver and a take approval each name the exact content they accepted."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.project, self.path = make_project(self.root)
        (self.root / "SH01.mp4").write_bytes(b"clip one")
        self.project["shots"][0]["versions"][0]["video"] = "SH01.mp4"

    def tearDown(self):
        self.tmp.cleanup()

    def waived(self):
        reviewed = review.record_verdict(self.project, self.path, FAILING_VERDICT)
        return review.approve(reviewed, self.path, "go", waive_review=True)

    def test_waiver_records_the_digest_of_the_review_it_accepts(self):
        approved = self.waived()
        self.assertEqual(
            approved["storyboard_approval"]["waived_review"]["digest"],
            review.review_digest(approved["storyboard_review"]),
        )

    def test_a_review_changed_under_the_same_time_voids_the_waiver(self):
        approved = self.waived()
        approved["storyboard_review"]["findings"].append({**BLOCKING_FINDING, "relationship": "Another failure"})
        self.assertTrue(review.gate(approved, self.path, None))

    def test_an_old_waiver_without_a_digest_still_matches_by_time(self):
        approved = self.waived()
        del approved["storyboard_approval"]["waived_review"]["digest"]
        self.assertEqual(review.gate(approved, self.path, None), [])

    def feedback(self, status):
        return {
            "project_id": "test-film",
            "base_revision": 1,
            "shots": [
                {"id": "SH01", "base_selected": "v001", "selected": "v001", "review_status": status, "notes": ""}
            ],
        }

    def test_an_approved_take_is_pinned_to_its_media_bytes(self):
        out = review.apply_feedback(self.project, self.feedback("approved"), self.path)
        version = out["shots"][0]["versions"][0]
        self.assertEqual(version["approved_sha256"], review.file_sha256(self.root, "SH01.mp4"))
        self.assertEqual(review.void_approvals(out, self.path), [])

    def test_changed_media_voids_the_take_approval(self):
        out = review.apply_feedback(self.project, self.feedback("approved"), self.path)
        (self.root / "SH01.mp4").write_bytes(b"clip one, regenerated")
        self.assertEqual(review.void_approvals(out, self.path), [("SH01", "v001")])

    def test_the_board_shows_a_void_approval_as_unreviewed(self):
        out = review.apply_feedback(self.project, self.feedback("approved"), self.path)
        (self.root / "SH01.mp4").write_bytes(b"clip one, regenerated")
        page = review.build(out, self.path).read_text()
        line = next(line for line in page.splitlines() if line.startswith("const P="))
        version = json.loads(line[len("const P=") : -1])["shots"][0]["versions"][0]
        self.assertEqual((version["review_status"], version["approval_void"]), ("unreviewed", True))
        self.assertEqual(out["shots"][0]["versions"][0]["review_status"], "approved")

    def test_a_take_no_longer_approved_drops_its_pin(self):
        out = review.apply_feedback(self.project, self.feedback("approved"), self.path)
        out = review.apply_feedback(out, {**self.feedback("revise"), "base_revision": 2}, self.path)
        self.assertNotIn("approved_sha256", out["shots"][0]["versions"][0])

    def test_an_approval_from_before_pinning_is_not_void(self):
        self.project["shots"][0]["versions"][0]["review_status"] = "approved"
        self.assertEqual(review.void_approvals(self.project, self.path), [])


def make_creator_project(root, profile="short"):
    """A two-shot short with a package and beats that pass the creator lint."""
    project, path = make_project(root)
    project["settings"].update(profile=profile, promise_by_seconds=4)
    project["package"] = {
        "title": "I Missed My Stop",
        "thumbnail": {"brief": "Her face against the bus window, the stop sign behind"},
    }
    project["beats"] = [
        {"id": "B0", "role": "promise", "shots": ["SH01"], "energy": 4},
        {"id": "B1", "role": "setup", "shots": ["SH01"], "energy": 3, "sets_up": ["B2"]},
        {"id": "B2", "role": "payoff", "shots": ["SH02"], "energy": 5},
    ]
    path.write_text(json.dumps(project))
    return project, path


class ProfileTest(unittest.TestCase):
    """settings.profile picks drama (the default) or short; short adds the beat lint."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def problems(self, project):
        return review.beat_problems(project)

    def test_a_project_without_a_profile_is_drama_and_skips_the_beat_lint(self):
        project, path = make_project(self.root)
        project["beats"] = [{"id": "B1", "role": "nonsense", "shots": ["SH99"]}]
        self.assertEqual(review.profile(project), "drama")
        reviewed = review.record_verdict(project, path, PASSING_VERDICT)
        self.assertEqual(review.readiness(reviewed, path), [])

    def test_only_drama_and_short_are_known_profiles(self):
        project, _ = make_project(self.root)
        for profile in ("long-form", "vlog"):
            with self.subTest(profile=profile):
                project["settings"]["profile"] = profile
                with self.assertRaisesRegex(ValueError, r"settings.profile must be one of \['drama', 'short'\]"):
                    review.validate(project)

    def test_a_complete_short_is_ready(self):
        project, path = make_creator_project(self.root)
        self.assertEqual(self.problems(project), [])
        self.assertEqual(review.readiness(review.record_verdict(project, path, PASSING_VERDICT), path), [])

    def test_a_short_with_a_broken_beat_plan_is_not_ready(self):
        project, path = make_creator_project(self.root)
        del project["beats"][0]
        reviewed = review.record_verdict(project, path, PASSING_VERDICT)
        self.assertTrue(any("promise" in p for p in review.readiness(reviewed, path)))

    def test_the_package_needs_a_title_and_a_thumbnail_brief(self):
        for field in ("title", "thumbnail"):
            with self.subTest(field=field):
                project, _ = make_creator_project(self.root)
                del project["package"][field]
                self.assertTrue(any(field in p for p in self.problems(project)))

    def test_the_promise_must_end_within_the_default_three_seconds(self):
        project, _ = make_creator_project(self.root)
        del project["settings"]["promise_by_seconds"]
        self.assertTrue(any("promise" in p and "3" in p for p in self.problems(project)))

    def test_every_setup_needs_a_later_payoff(self):
        project, _ = make_creator_project(self.root)
        project["beats"][1]["sets_up"] = []
        self.assertTrue(any("B1" in p and "payoff" in p for p in self.problems(project)))

    def test_a_setup_cannot_name_an_earlier_payoff(self):
        project, _ = make_creator_project(self.root)
        project["beats"][1]["shots"] = ["SH02"]
        project["beats"][2]["shots"] = ["SH01"]
        self.assertTrue(any("B1" in p and "later" in p for p in self.problems(project)))

    def test_every_payoff_needs_a_setup(self):
        project, _ = make_creator_project(self.root)
        project["beats"][1]["role"] = "turn"
        self.assertTrue(any("B2" in p and "setup" in p for p in self.problems(project)))

    def test_the_last_beat_is_a_payoff(self):
        project, _ = make_creator_project(self.root)
        project["beats"].append({"id": "B3", "role": "other", "shots": ["SH02"], "energy": 2})
        self.assertTrue(any("last" in p for p in self.problems(project)))

    def test_roles_energy_and_shots_are_checked(self):
        project, _ = make_creator_project(self.root)
        project["beats"][0].update(role="hook", energy=9, shots=["SH99"])
        problems = " ".join(self.problems(project))
        for expected in ("hook", "energy", "SH99"):
            self.assertIn(expected, problems)

    def test_a_short_runs_at_most_sixty_seconds(self):
        project, _ = make_creator_project(self.root)
        project["shots"][1]["duration"] = 60
        self.assertTrue(any("60" in p for p in self.problems(project)))

    def test_a_critical_component_must_map_to_a_beat(self):
        project, _ = make_creator_project(self.root)
        project["package"]["critical"] = [{"item": "the stop sign", "beats": ["B9"]}]
        self.assertTrue(any("stop sign" in p for p in self.problems(project)))

    def test_footage_shots_skip_the_storyboard_gates(self):
        project, path = make_project(self.root)
        project["shots"][1]["source"] = "footage"
        review.validate(project)
        self.assertEqual(review.staging_problems(project), [])
        self.assertEqual(review.card_problems(project), [])
        self.assertEqual(sorted(review.shot_digests(project, path)), ["SH01"])
        approved = review.approve(review.record_verdict(project, path, PASSING_VERDICT), path, "Approved.")
        self.assertEqual(review.gate(approved, path, None), [])

    def test_a_generated_shot_still_obeys_the_shot_ceiling(self):
        project, _ = make_project(self.root)
        project["shots"][0]["duration"] = 7
        project["shots"][1]["start"] = 7
        project["shots"][1]["duration"] = 1
        with self.assertRaisesRegex(ValueError, "SH01"):
            review.validate(project)

    def test_build_fills_the_profile_aspect_when_unset(self):
        project, path = make_creator_project(self.root)
        page = review.build(project, path).read_text()
        line = next(line for line in page.splitlines() if line.startswith("const P="))
        self.assertEqual(json.loads(line[len("const P=") : -1])["settings"]["aspect_ratio"], "9:16")

    def test_beats_command_prints_minute_marks_and_fails_on_problems(self):
        project, path = make_creator_project(self.root)
        run = subprocess.run([sys.executable, str(SCRIPT), "beats", str(path)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("0:00", run.stdout)
        del project["package"]
        path.write_text(json.dumps(project))
        run = subprocess.run([sys.executable, str(SCRIPT), "beats", str(path)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)


class ProducerReadyTest(unittest.TestCase):
    """Cast and sound checks join the blind board review before a board reaches the producer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.project, self.path = make_project(self.root)
        add_cast(self.project, self.root)
        add_line(self.project, self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def board_reviewed(self):
        return review.record_verdict(self.project, self.path, PASSING_VERDICT)

    def all_checked(self):
        checked = review.record_check(self.board_reviewed(), self.path, "cast", PASSING_CHECK)
        return review.record_check(checked, self.path, "sound", PASSING_CHECK)

    def test_film_with_cast_needs_a_cast_check(self):
        problems = review.readiness(self.board_reviewed(), self.path)
        self.assertTrue(any("cast check" in p for p in problems))

    def test_film_with_sound_needs_a_sound_check(self):
        problems = review.readiness(self.board_reviewed(), self.path)
        self.assertTrue(any("sound check" in p for p in problems))

    def test_passing_checks_make_the_board_ready(self):
        self.assertEqual(review.readiness(self.all_checked(), self.path), [])

    def test_failing_cast_check_keeps_the_board_not_ready(self):
        failing = {"verdict": "fail", "findings": [{**PASSING_FINDING, "result": "fail"}]}
        checked = review.record_check(self.all_checked(), self.path, "cast", failing)
        problems = review.readiness(checked, self.path)
        self.assertTrue(any("cast check failed" in p for p in problems))

    def test_changed_reference_view_reopens_the_cast_check(self):
        checked = self.all_checked()
        (self.root / "LEAD-back.png").write_bytes(b"regenerated back view")
        problems = review.readiness(checked, self.path)
        self.assertTrue(any("cast check" in p and "LEAD-back.png" in p for p in problems))

    def test_changed_line_take_reopens_the_sound_check(self):
        checked = self.all_checked()
        (self.root / "L1.wav").write_bytes(b"new take")
        problems = review.readiness(checked, self.path)
        self.assertTrue(any("sound check" in p and "L1.wav" in p for p in problems))

    def test_changed_effect_reopens_the_sound_check(self):
        checked = self.all_checked()
        (self.root / "door.wav").write_bytes(b"softer bang")
        self.assertTrue(review.readiness(checked, self.path))

    def test_sound_check_refuses_a_line_without_direction(self):
        self.project["shots"][1]["dialogue"][0]["direction"] = " "
        with self.assertRaisesRegex(ValueError, "direction"):
            review.record_check(self.board_reviewed(), self.path, "sound", PASSING_CHECK)

    def test_sound_check_refuses_a_line_without_audio(self):
        del self.project["shots"][1]["dialogue"][0]["audio"]
        with self.assertRaisesRegex(ValueError, "audio"):
            review.record_check(self.board_reviewed(), self.path, "sound", PASSING_CHECK)

    def test_unknown_check_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            review.record_check(self.project, self.path, "lighting", PASSING_CHECK)

    def test_check_with_a_failed_finding_cannot_pass(self):
        with self.assertRaises(ValueError):
            review.record_check(
                self.project,
                self.path,
                "cast",
                {"verdict": "pass", "findings": [{**PASSING_FINDING, "result": "fail"}]},
            )

    def test_approval_requires_the_checks(self):
        with self.assertRaises(ValueError):
            review.approve(self.board_reviewed(), self.path, "Approved storyboard v003, go ahead.")

    def test_check_command_records_the_verdict(self):
        self.path.write_text(json.dumps(self.board_reviewed()))
        verdict = self.root / "cast.json"
        verdict.write_text(json.dumps(PASSING_CHECK))
        run = subprocess.run(
            [sys.executable, str(SCRIPT), "check", str(self.path), "cast", str(verdict)], capture_output=True, text=True
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(self.path.read_text())["checks"]["cast"]["verdict"], "pass")


if __name__ == "__main__":
    unittest.main()
