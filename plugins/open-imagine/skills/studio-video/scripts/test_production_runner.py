"""No model, network or real GPU-token access in these checks."""

import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
import production_runner as runner
import review
from test_review import PASSING_VERDICT, make_project


class ProductionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.data, self.project = make_project(self.root)
        self.data["settings"].update(video_attempt_limit=6, video_attempts_per_shot=2)
        self.project.write_text(json.dumps(self.data))
        self.job = {
            "name": "proof",
            "shot": "SH01",
            "out": "take.mp4",
            "allowance_seconds": 90,
            "request": {"kind": "video", "mode": "i2v", "seed": 1},
            "references": [{"path": "SH01.png", "frame_index": 0, "strength": 1}],
        }
        self.slot = Mock(spec=runner.Slot, deadline=time.monotonic() + 1000)

    def approve_fixture(self):
        self.data["shots"][0]["staging"]["submission_spec"] = runner.job_spec(self.job)
        self.data = review.record_verdict(self.data, self.project, PASSING_VERDICT)
        self.data = review.approve(self.data, self.project, "Synthetic test fixture approval")
        self.project.write_text(json.dumps(self.data))

    def test_two_token_contenders_have_one_owner(self):
        path = self.root / "token"
        a, b = runner.Token(path, "a", 1), runner.Token(path, "b", 1)
        a.acquire()
        with self.assertRaises(FileExistsError):
            b.acquire()
        self.assertEqual(path.read_text(), a.text)
        with self.assertRaises(RuntimeError):
            b.release()
        a.release()
        self.assertFalse(path.exists())

    def test_replaced_token_is_not_removed(self):
        path = self.root / "token"
        token = runner.Token(path, "a", 1)
        token.acquire()
        path.write_text("someone else")
        with self.assertRaises(RuntimeError):
            token.release()
        self.assertEqual(path.read_text(), "someone else")

    def test_repo_resolution_order(self):
        checkout = self.root / "checkout"
        checkout.mkdir()
        (checkout / "studio.toml").write_text("")
        other = self.root / "other"
        other.mkdir()
        with patch.dict("os.environ", {"STUDIO_REPO": str(other)}):
            self.assertEqual(runner.resolve_repo(str(checkout)), checkout.resolve())
            with self.assertRaises(SystemExit):
                runner.resolve_repo(str(other))
        with patch.dict("os.environ", {"STUDIO_REPO": str(checkout)}):
            self.assertEqual(runner.resolve_repo(), checkout.resolve())
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(Path, "cwd", lambda: checkout),
        ):
            self.assertEqual(runner.resolve_repo(), checkout.resolve())
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(Path, "cwd", lambda: other),
            self.assertRaises(SystemExit),
        ):
            runner.resolve_repo()

    def test_direct_submission_without_review_cannot_post(self):
        with self.assertRaises(ValueError):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()

    def test_real_gate_rejects_stale_frame_before_post(self):
        self.approve_fixture()
        (self.root / "SH01.png").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "gate closed"):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()

    def test_actual_request_must_match_reviewed_job(self):
        self.approve_fixture()
        job = copy.deepcopy(self.job)
        job["request"]["seed"] = 2
        with self.assertRaisesRegex(ValueError, "differs"):
            runner.run_job(self.slot, self.project, job)
        self.slot.call.assert_not_called()

    def test_gate_is_checked_on_each_job(self):
        self.approve_fixture()
        runner.gate_job(self.project, self.job)
        self.data["shots"][0]["duration"] = 3
        self.project.write_text(json.dumps(self.data))
        with self.assertRaises(RuntimeError):
            runner.gate_job(self.project, self.job)

    def test_timed_out_post_is_not_retried(self):
        self.approve_fixture()
        self.slot.call.side_effect = TimeoutError("accepted status unknown")
        with self.assertRaises(TimeoutError):
            runner.run_job(self.slot, self.project, self.job)
        self.assertEqual(self.slot.call.call_count, 1)
        self.assertTrue((self.root / "take.mp4.run/client.json").exists())
        with self.assertRaises(FileExistsError):
            runner.run_job(self.slot, self.project, self.job)
        self.assertEqual(self.slot.call.call_count, 1)

    def test_corrupt_completed_file_cannot_be_resumed(self):
        self.approve_fixture()
        folder = self.root / "take.mp4.run"
        folder.mkdir()
        runner.save(folder / "complete.json", {"signature": "other", "sha256": "bad"})
        (self.root / "take.mp4").write_bytes(b"broken")
        with self.assertRaises(ValueError):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()

    def test_job_that_will_not_fit_never_posts(self):
        self.slot.deadline = time.monotonic() + 1
        with self.assertRaisesRegex(RuntimeError, "does not fit"):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()

    def test_export_registration_preserves_shot_definitions(self):
        (self.root / "preview.mp4").write_bytes(b"fixture")
        before = review.shot_digests(self.data, self.project)
        with patch.object(runner, "validate_media"), patch.object(runner.subprocess, "run") as build:
            runner.register_export(self.project, "preview.mp4", "Timed storyboard", "animatic")
        after = json.loads(self.project.read_text())
        self.assertEqual(before, review.shot_digests(after, self.project))
        self.assertEqual(after["exports"][0]["path"], "preview.mp4")
        self.assertEqual(after["exports"][0]["sha256"], runner.digest(b"fixture"))
        build.assert_called_once()

    def test_paths_cannot_escape_project(self):
        for value in ("../outside.png", ".env", "assets/.env.secret"):
            with self.assertRaises(ValueError):
                runner.local(self.root, value)

    def test_video_budget_blocks_third_attempt_even_if_gate_would_pass(self):
        self.approve_fixture()
        for number in (1, 2):
            folder = self.root / f"prior-{number}"
            folder.mkdir()
            runner.save(folder / "submitted.json", {"kind": "video", "shot": "SH01"})
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()

    def test_batch_cannot_bypass_per_job_gate_or_budget(self):
        self.job["request"]["items"] = [{"prompt": "one"}, {"prompt": "two"}]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()

    def test_cpu_only_stub_does_not_hide_a_real_gpu_server(self):
        listing = "PID COMMAND\n11 uv run studio --stub --port 8823\n12 python /x/bin/studio --port 8818\n"
        with patch.object(runner.subprocess, "check_output", return_value=listing):
            self.assertEqual(runner.busy_processes(), ["12 python /x/bin/studio --port 8818"])

    def test_owned_server_cannot_submit_after_token_changes(self):
        slot = runner.Slot(self.root, "fixture", 1)
        slot.token = runner.Token(self.root / "token", "fixture", 1)
        slot.server = Mock()
        slot.server.poll.return_value = None
        slot.token.acquire()
        slot.assert_owned()
        slot.token.path.write_text("foreign owner")
        with self.assertRaisesRegex(RuntimeError, "Own live server"):
            slot.assert_owned()

    def test_changed_reviewed_end_guide_blocks_submission(self):
        self.approve_fixture()
        guide = self.root / "end.png"
        guide.write_bytes(b"reviewed end state")
        self.data["shots"][0]["staging"]["review_media_sha256"] = {"end.png": runner.digest(guide.read_bytes())}
        self.data = review.record_verdict(self.data, self.project, PASSING_VERDICT)
        self.data = review.approve(self.data, self.project, "Synthetic test fixture approval")
        self.project.write_text(json.dumps(self.data))
        guide.write_bytes(b"changed end state")
        with self.assertRaisesRegex(ValueError, "Reviewed guide changed"):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()

    def test_cpu_only_cli_never_constructs_slot(self):
        self.data["execution_constraints"] = {"gpu_allowed": False}
        self.project.write_text(json.dumps(self.data))
        for command in (["run", "planned.json"], ["discover"]):
            with (
                self.subTest(command=command),
                patch.object(runner, "Slot") as slot_class,
                patch.object(runner.sys, "argv", ["production_runner.py", str(self.project), *command]),
            ):
                with self.assertRaisesRegex(RuntimeError, "CPU preparation only"):
                    runner.main()
                slot_class.assert_not_called()

    def test_cpu_only_direct_helper_never_reads_inputs_or_posts(self):
        self.data["execution_constraints"] = {"gpu_allowed": False}
        self.project.write_text(json.dumps(self.data))
        self.job["references"] = [{"path": "does-not-exist.png"}]
        with self.assertRaisesRegex(RuntimeError, "CPU preparation only"):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()
        self.assertFalse((self.root / "take.mp4.run").exists())

    def test_generation_hold_applies_to_images_before_any_submission(self):
        self.data["generation_hold"] = {
            "scope": ["image", "voice", "video"],
            "resume_requires": "new producer decision",
        }
        self.project.write_text(json.dumps(self.data))
        self.job["request"]["kind"] = "image"
        with self.assertRaisesRegex(RuntimeError, "Generation is on hold"):
            runner.run_job(self.slot, self.project, self.job)
        self.slot.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
