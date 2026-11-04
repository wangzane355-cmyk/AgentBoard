"""Real local verification with fake model replies. Never invokes an AI service."""
import copy
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from autonomy import AutonomyService, parse_review, validate_policy, public_mission
from autonomy_store import MissionStore
from supervised_process import process_stamp, same_process
from verification import validate_checks, verification_files, verification_unchanged, command_argv


class FixtureRuntime:
    def __init__(self, root):
        self.root = Path(root)
        self.calls, self.updates = [], []
        self.builds = [41, 42]
        self.reviews = ["pass"]
        self.interrupt = None
        self.tamper = False
        self.drift = False
        self.service = None

    def attach(self, mission):
        pass

    def publish(self, mission):
        self.updates.append(copy.deepcopy(mission))

    def can_start(self):
        return True

    def ready(self, mission):
        return True

    def folder(self, mission):
        folder = self.root / "runs" / mission["id"]
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def prepare(self, mission):
        workspace = self.root / "work" / mission["id"]
        workspace.mkdir(parents=True)
        (workspace / "sample.py").write_text("value = 0\n", encoding="utf-8")
        (workspace / "test_sample.py").write_text(
            "import unittest\nimport sample\nclass FixedTest(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(sample.value,42)\n", encoding="utf-8")
        return {"workspace": str(workspace), "source_before": {"sample.py": "original"}}

    def workspace_digest(self, mission):
        return (Path(mission["workspace"]) / "sample.py").read_text(encoding="utf-8")

    def integrity(self, mission):
        return {"safe": not self.drift, "error": "original project changed" if self.drift else "",
                "changes": [{"path": "sample.py", "change": "modified"}],
                "source_unchanged": not self.drift, "protected_unchanged": True}

    def preflight(self, mission):
        pass

    def invoke(self, mission, stage, folder, runner):
        self.calls.append((stage, mission["attempt"]))
        if stage == "plan":
            answer = json.dumps({"summary": "Fix the value", "steps": ["Read fixed tests", "Fix value", "Verify"], "risks": []})
        elif stage == "build":
            value = self.builds[min(mission["attempt"] - 1, len(self.builds) - 1)]
            (Path(mission["workspace"]) / "sample.py").write_text(f"value = {value}\n# attempt {mission['attempt'] if len(self.builds)>1 else 'same'}\n", encoding="utf-8")
            if self.tamper:
                (Path(mission["workspace"]) / "test_sample.py").write_text("# forged test\n", encoding="utf-8")
            if self.interrupt:
                action, self.interrupt = self.interrupt, None
                self.service.action(mission["id"], action)
            answer = "Implemented\nAGENTBOARD_STATUS: DONE"
        else:
            count = len([call for call in self.calls if call[0] == "review"])
            verdict = self.reviews[min(count - 1, len(self.reviews) - 1)]
            answer = json.dumps({"verdict": verdict, "summary": "Reviewed actual source",
                "findings": [] if verdict == "pass" else [{"severity": "medium", "file": "sample.py", "detail": "Add the documented edge case"}]})
        return {"exit_code": 0, "answer": answer, "metadata": {"session_id": f"fixture-{len(self.calls)}"}}

    def decision(self, answer):
        return None

    def receipt(self, mission, integrity):
        return {"summary": "Verified", "tests": sum(c.get("tests") or 0 for c in mission["checks"]), "attempts": mission["attempt"]}


class AutonomousFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = FixtureRuntime(self.root)
        self.service = AutonomyService(self.root / "data", self.runtime)
        self.runtime.service = self.service
        self.task = {"id": "task-fixture", "project_id": "project-fixture", "title": "Fix sample", "description": "Make value 42"}
        self.policy = {"checks": [{"kind": "python_unittest", "name": "Fixed behavioral tests", "modules": ["test_sample"]}],
                       "max_attempts": 3, "total_minutes": 5, "attempt_minutes": 1}

    def create(self):
        return self.service.create(self.task, self.policy, auto_start=True)

    def execute(self, mission):
        self.service.execute(mission["id"])
        return self.service.store.get(mission["id"])

    def test_failure_repair_independent_tests_and_review_deliver(self):
        mission = self.execute(self.create())
        self.assertEqual(mission["phase"], "review")
        self.assertEqual(mission["attempt"], 2)
        self.assertEqual(mission["receipt"]["tests"], 1)
        self.assertTrue(mission["checks"][0]["passed"])
        self.assertEqual([stage for stage, _ in self.runtime.calls], ["plan", "build", "build", "review"])
        self.assertTrue(verification_unchanged(mission["workspace"], mission["verification_manifest"]))
        self.assertEqual(len(mission["history"]), 1)
        self.assertEqual(self.service.store.events(mission["id"])[-1]["kind"], "delivered")

    def test_independent_review_can_send_passing_code_back(self):
        self.runtime.builds = [42, 42]
        self.runtime.reviews = ["changes_requested", "pass"]
        mission = self.execute(self.create())
        self.assertEqual(mission["phase"], "review")
        self.assertEqual(mission["attempt"], 2)
        self.assertEqual(len([call for call in self.runtime.calls if call[0] == "review"]), 2)
        self.assertIn("独立审查", mission["history"][0]["reason"])

    def test_recheck_keeps_implementation_and_previous_evidence(self):
        self.runtime.builds = [42]
        mission = self.execute(self.create())
        previous_stdout = mission["checks"][0]["stdout"]
        calls_before = list(self.runtime.calls)
        self.service.action(mission["id"], "recheck")
        mission = self.execute(mission)
        self.assertEqual(mission["phase"], "review")
        self.assertEqual(mission["attempt"], 1)
        self.assertEqual(self.runtime.calls, calls_before + [("review", 1)])
        self.assertNotEqual(mission["checks"][0]["stdout"], previous_stdout)
        self.assertTrue(Path(previous_stdout).is_file())
        self.assertEqual(mission["previous_deliveries"][0]["receipt"]["tests"], 1)

    def test_protected_test_tampering_blocks_before_acceptance(self):
        self.runtime.tamper = True
        mission = self.execute(self.create())
        self.assertEqual(mission["phase"], "blocked")
        self.assertTrue(mission["fatal"])
        self.assertNotIn("review", [call[0] for call in self.runtime.calls])
        with self.assertRaises(ValueError):
            self.service.action(mission["id"], "resume")

    def test_identical_failure_and_source_stops_without_endless_calls(self):
        self.runtime.builds = [0]
        mission = self.execute(self.create())
        self.assertEqual(mission["phase"], "blocked")
        self.assertEqual(mission["attempt"], 2)
        self.assertIn("没有有效进展", mission["error"])

    def test_retry_budget_is_not_reset_by_resume(self):
        self.policy["max_attempts"] = 1
        mission = self.execute(self.create())
        self.assertEqual(mission["attempt"], 1)
        self.assertEqual(mission["phase"], "blocked")
        with self.assertRaises(ValueError):
            self.service.action(mission["id"], "resume")

    def test_pause_and_resume_reuses_workspace_without_duplicate_build(self):
        self.runtime.builds = [42]
        self.runtime.interrupt = "pause"
        mission = self.execute(self.create())
        self.assertEqual(mission["phase"], "paused")
        workspace = mission["workspace"]
        self.assertEqual(mission["next_phase"], "check")
        self.service.action(mission["id"], "resume")
        mission = self.execute(mission)
        self.assertEqual(mission["phase"], "review")
        self.assertEqual(mission["workspace"], workspace)
        self.assertEqual(len([call for call in self.runtime.calls if call[0] == "build"]), 1)

    def test_stop_never_schedules_checker_or_reviewer(self):
        self.runtime.interrupt = "stop"
        mission = self.execute(self.create())
        self.assertEqual(mission["phase"], "cancelled")
        self.assertEqual([call[0] for call in self.runtime.calls], ["plan", "build"])
        with self.assertRaises(ValueError):
            self.service.action(mission["id"], "resume")

    def test_total_budget_stops_before_any_model_call(self):
        mission = self.create()
        self.service.store.update(mission["id"], {"spent_seconds": 301})
        mission = self.execute(mission)
        self.assertEqual(mission["phase"], "blocked")
        self.assertEqual(self.runtime.calls, [])

    def test_source_drift_stops_and_records_fatal_evidence(self):
        self.runtime.drift = True
        mission = self.execute(self.create())
        self.assertTrue(mission["fatal"])
        self.assertEqual(mission["phase"], "blocked")
        self.assertEqual(self.runtime.calls, [])

    def test_durable_checkpoint_recovers_after_new_service_instance(self):
        self.runtime.builds = [42]
        self.runtime.interrupt = "pause"
        mission = self.execute(self.create())
        self.service.store.update(mission["id"], {"phase": "checking", "control": "run", "stage_started_at": None})
        replacement = AutonomyService(self.root / "data", self.runtime)
        self.runtime.service = replacement
        replacement._recover()
        recovered = replacement.store.get(mission["id"])
        self.assertTrue(recovered["recovered"])
        self.assertEqual(recovered["phase"], "queued")
        replacement.execute(mission["id"])
        self.assertEqual(replacement.store.get(mission["id"])["phase"], "review")
        self.assertEqual(len([call for call in self.runtime.calls if call[0] == "build"]), 1)

    def test_recovery_does_not_kill_reused_pid(self):
        mission = self.create()
        self.service.store.update(mission["id"], {"phase": "building", "active_processes": [{"pid": 123, "stamp": "old"}]})
        with patch("autonomy.process_stamp", return_value="new"), patch("autonomy.terminate_record") as stop:
            self.service._recover()
        stop.assert_not_called()

    def test_recovery_terminates_only_identity_matched_worker(self):
        mission = self.create()
        record = {"pid": 123, "stamp": "matched"}
        self.service.store.update(mission["id"], {"phase": "building", "active_processes": [record]})
        with patch("autonomy.process_stamp", return_value="matched"), patch("autonomy.terminate_record", return_value=True) as stop:
            self.service._recover()
        stop.assert_called_once_with(record)

    def test_saved_manual_pause_is_not_automatically_resumed(self):
        mission = self.create()
        self.service.store.update(mission["id"], {"phase": "building", "control": "pause"})
        self.service._recover()
        self.assertEqual(self.service.store.get(mission["id"])["phase"], "paused")

    def test_public_state_excludes_source_hashes_and_context(self):
        mission = self.execute(self.create())
        public = public_mission(mission)
        for key in ("source_before", "baseline", "verification_manifest", "task_snapshot"):
            self.assertNotIn(key, public)

    def test_two_bounded_workers_claim_each_mission_only_once(self):
        service = AutonomyService(self.root / "parallel-data", self.runtime, max_workers=2)
        self.runtime.service = service
        self.runtime.builds = [42]
        original_invoke = self.runtime.invoke
        barrier = threading.Barrier(2)
        def synchronized(mission, stage, folder, runner):
            if stage == "build":
                barrier.wait(timeout=8)
            return original_invoke(mission, stage, folder, runner)
        self.runtime.invoke = synchronized
        first = service.create(self.task, self.policy, auto_start=True)
        second = service.create({**self.task, "id": "second-fixture"}, self.policy, auto_start=True)
        service.start()
        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and any(m["phase"] not in ("review", "blocked") for m in service.store.all()):
                time.sleep(0.05)
            self.assertEqual(service.store.get(first["id"])["phase"], "review")
            self.assertEqual(service.store.get(second["id"])["phase"], "review")
            self.assertEqual(len([call for call in self.runtime.calls if call[0] == "build"]), 2)
        finally:
            service.stop()

    def test_second_live_supervisor_is_rejected(self):
        self.service.start()
        other = AutonomyService(self.root / "data", self.runtime)
        try:
            with self.assertRaises(RuntimeError):
                other.start()
        finally:
            self.service.stop()


class StoreAndPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = MissionStore(self.tmp.name)

    def test_checkpoints_and_events_survive_reopening(self):
        self.store.create({"id": "test", "phase": "queued"})
        self.store.update("test", {"phase": "checking"}, "checking", "Run fixed tests")
        reopened = MissionStore(self.tmp.name)
        self.assertEqual(reopened.get("test")["phase"], "checking")
        self.assertEqual(len(reopened.events("test")), 2)

    def test_stale_revision_cannot_overwrite_control(self):
        self.store.create({"id": "test", "control": "run"})
        self.store.update("test", {"control": "pause"})
        with self.assertRaises(ValueError):
            self.store.update("test", {"control": "run"}, revision=0)

    def test_second_live_scheduler_cannot_claim_same_database(self):
        self.store.claim_owner({"token": "one", "pid": 1, "stamp": "a"}, lambda _: True)
        with self.assertRaises(RuntimeError):
            self.store.claim_owner({"token": "two", "pid": 2, "stamp": "b"}, lambda _: True)
        self.store.claim_owner({"token": "two", "pid": 2, "stamp": "b"}, lambda _: False)

    def test_process_stamp_matches_current_process(self):
        stamp = process_stamp(os.getpid())
        if os.name == "nt" or Path("/proc").is_dir():
            self.assertTrue(stamp)
            self.assertTrue(same_process({"pid": os.getpid(), "stamp": stamp}))
            self.assertFalse(same_process({"pid": os.getpid(), "stamp": "wrong"}))

    def test_readonly_review_cannot_claim_pass_with_serious_findings(self):
        result = parse_review(json.dumps({"verdict": "pass", "summary": "A concrete review", "findings": [
            {"severity": "high", "file": "x.py", "detail": "incorrect output"}]}))
        self.assertEqual(result["verdict"], "changes_requested")

    def test_behavioral_checks_are_required(self):
        with self.assertRaises(ValueError):
            validate_checks([{"kind": "python_compile"}])
        with self.assertRaises(ValueError):
            validate_checks([])

    def test_check_arguments_do_not_allow_shell_or_python_code(self):
        for command in (["cmd", "/c", "echo ok"], ["python", "-c", "print(1)"], ["npm", "install"], ["powershell", "-Command", "x"]):
            with self.subTest(command=command), self.assertRaises(ValueError):
                command_argv(command)

    def test_path_and_viewport_validation(self):
        for start in ("../outside", "C:/private", "/tmp", "tests\\outside"):
            with self.subTest(start=start), self.assertRaises(ValueError):
                validate_checks([{"kind": "python_unittest", "start_dir": start}])
        with self.assertRaises(ValueError):
            validate_checks([{"kind": "web", "expected_text": []}])

    def test_time_and_retry_bounds(self):
        policy = {"checks": [{"kind": "python_unittest"}], "attempt_minutes": 26}
        with self.assertRaises(ValueError):
            validate_policy(policy)
        policy.update(attempt_minutes=25, max_attempts=999)
        with self.assertRaises(ValueError):
            validate_policy(policy)


if __name__ == "__main__":
    unittest.main()
