"""Task/project recycle-bin integrity checks. No model, runtime or file mutation."""
import copy
import unittest
from pathlib import Path

from task_archive import archive_project, archive_task, restore_project, restore_task


NOW = "2026-11-03T23:00:00+00:00"
LATER = "2026-11-03T23:01:00+00:00"


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.state = {"projects": [{"id": "p", "name": "One", "path": "fixture-source", "context_files": ["brief.md"]},
                                   {"id": "q", "name": "Two"}],
                      "tasks": [{"id": "a", "project_id": "p", "title": "First card", "status": "review",
                                 "auto_start": True, "depends_on": [], "run_ids": ["run-a"], "description": "Keep this goal"}],
                      "runs": [{"id": "run-a", "task_id": "a", "status": "review",
                                "promotion": {"file.txt": {"before": "original", "after": "delivery"}},
                                "receipt": {"tests": 4}, "workspace": "fixture-worker"}],
                      "chats": []}

    def assert_rejected_without_mutation(self, action):
        before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError):
            action()
        self.assertEqual(self.state, before)

    def test_task_delete_and_restore_preserve_delivery_history_and_do_not_autostart(self):
        before = copy.deepcopy(self.state)
        task = archive_task(self.state, "a", NOW)
        self.assertEqual(task["deleted_at"], NOW)
        self.assertEqual(task["status"], "review")
        self.assertEqual(task["deleted_from_status"], "review")
        self.assertTrue(task["deleted_auto_start"])
        self.assertFalse(task["auto_start"])
        self.assertEqual(self.state["runs"], before["runs"])
        restored = restore_task(self.state, "a", LATER)
        self.assertIs(restored, task)
        self.assertIsNone(task["deleted_at"])
        self.assertEqual(task["run_ids"], ["run-a"])
        self.assertEqual(task["description"], "Keep this goal")
        self.assertEqual(task["restored_at"], LATER)
        self.assertFalse(task["auto_start"])

    def test_completed_integrated_card_can_be_hidden_without_rollback(self):
        self.state["tasks"][0]["status"] = "done"
        self.state["runs"][0]["status"] = "accepted"
        runs = copy.deepcopy(self.state["runs"])
        archive_task(self.state, "a", NOW)
        self.assertEqual(self.state["runs"], runs)
        self.assertEqual(self.state["tasks"][0]["status"], "done")

    def test_active_and_queued_task_or_run_cannot_be_deleted(self):
        for status in ("queued", "preparing", "running", "checking"):
            with self.subTest(status=status):
                self.state["tasks"][0]["status"] = status
                self.assert_rejected_without_mutation(lambda: archive_task(self.state, "a", NOW))
        self.state["tasks"][0]["status"] = "blocked"
        self.state["runs"][0]["status"] = "running"
        self.assert_rejected_without_mutation(lambda: archive_task(self.state, "a", NOW))

    def test_durable_active_mission_is_guarded_even_when_task_mirror_is_blocked(self):
        task = self.state["tasks"][0]
        task.update(mission_id="m", status="blocked")
        for phase in ("queued", "preparing", "planning", "building", "checking", "reviewing", "repairing"):
            with self.subTest(phase=phase):
                self.assert_rejected_without_mutation(lambda: archive_task(self.state, "a", NOW, {"id": "m", "task_id": "a", "phase": phase}))

    def test_paused_and_blocked_missions_can_be_hidden_without_changing_the_mission(self):
        self.state["tasks"][0].update(mission_id="m", status="blocked")
        for phase in ("paused", "blocked", "review", "accepted", "cancelled"):
            with self.subTest(phase=phase):
                state = copy.deepcopy(self.state)
                mission = {"id": "m", "task_id": "a", "phase": phase, "workspace_after": {"file": "hash"}}
                before = copy.deepcopy(mission)
                archive_task(state, "a", NOW, mission)
                self.assertEqual(mission, before)
                self.assertEqual(state["tasks"][0]["deleted_at"], NOW)

    def test_missing_or_mismatched_mission_rejects_before_mutation(self):
        self.state["tasks"][0]["mission_id"] = "m"
        for mission in (None, {}, {"id": "m", "phase": "unknown"}, {"id": "other", "phase": "paused"}, {"id": "m", "task_id": "other", "phase": "paused"}):
            with self.subTest(mission=mission):
                self.assert_rejected_without_mutation(lambda: archive_task(self.state, "a", NOW, mission))

    def test_dependency_blocker_names_the_card_and_preserves_state(self):
        self.state["tasks"].append({"id": "b", "project_id": "q", "title": "Needs the first card", "status": "done", "depends_on": ["a"]})
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "Needs the first card"):
            archive_task(self.state, "a", NOW)
        self.assertEqual(self.state, before)

    def test_deleted_dependency_cards_do_not_block_removal(self):
        self.state["tasks"].append({"id": "b", "project_id": "q", "title": "Hidden", "depends_on": ["a"], "deleted_at": NOW})
        archive_task(self.state, "a", NOW)
        self.assertEqual(self.state["tasks"][0]["deleted_at"], NOW)

    def test_idle_linked_chat_is_detached_without_losing_messages_or_consensus(self):
        chat = {"id": "c", "project_id": "p", "task_id": "a", "status": "idle",
                "messages": [{"text": "Keep history"}], "consensus": "Agreed plan", "batch": {"status": "done"}}
        self.state["chats"].append(chat)
        archive_task(self.state, "a", NOW)
        self.assertEqual(chat["task_id"], "")
        self.assertEqual(chat["detached_task_id"], "a")
        self.assertTrue(chat["consensus_needs_review"])
        self.assertEqual(chat["messages"], [{"text": "Keep history"}])
        self.assertEqual(chat["consensus"], "Agreed plan")
        restore_task(self.state, "a", LATER)
        self.assertEqual(chat["task_id"], "")

    def test_running_linked_chat_and_batch_block_deletion(self):
        for chat in ({"id": "c", "task_id": "a", "status": "running"},
                     {"id": "c", "task_id": "a", "status": "idle", "batch": {"status": "running"}},
                     {"id": "discussion", "task_id": "other", "status": "running"}):
            with self.subTest(chat=chat):
                self.state["chats"] = [chat]
                self.state["tasks"][0]["discussion_id"] = "discussion"
                self.assert_rejected_without_mutation(lambda: archive_task(self.state, "a", NOW))

    def test_task_restore_requires_the_parent_project_to_be_restored_first(self):
        archive_task(self.state, "a", NOW)
        archive_project(self.state, "p", NOW)
        self.assert_rejected_without_mutation(lambda: restore_task(self.state, "a", LATER))
        restore_project(self.state, "p", LATER)
        restore_task(self.state, "a", LATER)
        self.assertIsNone(self.state["tasks"][0]["deleted_at"])

    def test_project_delete_keeps_internal_dependencies_chats_runs_and_individual_deletions(self):
        self.state["tasks"].append({"id": "b", "project_id": "p", "title": "Internal dependent", "status": "ready",
                                    "auto_start": True, "depends_on": ["a"], "deleted_at": "earlier"})
        self.state["chats"].append({"id": "c", "project_id": "p", "task_id": "a", "status": "idle",
                                    "messages": [{"text": "Keep the project discussion"}], "consensus": "Original consensus"})
        chats, runs = copy.deepcopy(self.state["chats"]), copy.deepcopy(self.state["runs"])
        project = archive_project(self.state, "p", NOW)
        self.assertEqual(project["deleted_at"], NOW)
        self.assertEqual(project["path"], "fixture-source")
        self.assertEqual(project["context_files"], ["brief.md"])
        self.assertEqual(self.state["chats"], chats)
        self.assertEqual(self.state["runs"], runs)
        self.assertFalse(any(task["auto_start"] for task in self.state["tasks"]))
        restore_project(self.state, "p", LATER)
        self.assertEqual(self.state["tasks"][1]["deleted_at"], "earlier")
        self.assertFalse(any(task["auto_start"] for task in self.state["tasks"]))
        self.assertEqual(self.state["chats"], chats)

    def test_project_blocks_running_task_chat_and_orphan_active_mission(self):
        self.state["tasks"][0]["status"] = "queued"
        self.assert_rejected_without_mutation(lambda: archive_project(self.state, "p", NOW))
        self.state["tasks"][0]["status"] = "review"
        self.state["chats"] = [{"id": "c", "project_id": "p", "status": "running"}]
        self.assert_rejected_without_mutation(lambda: archive_project(self.state, "p", NOW))
        self.state["chats"] = []
        self.assert_rejected_without_mutation(lambda: archive_project(self.state, "p", NOW, [{"id": "orphan", "project_id": "p", "phase": "planning"}]))

    def test_project_durable_mission_state_is_required_and_active_mission_blocks(self):
        self.state["tasks"][0]["mission_id"] = "m"
        self.assert_rejected_without_mutation(lambda: archive_project(self.state, "p", NOW))
        self.assert_rejected_without_mutation(lambda: archive_project(self.state, "p", NOW, [{"id": "m", "task_id": "a", "phase": "building"}]))
        mission = {"id": "m", "task_id": "a", "project_id": "p", "phase": "paused"}
        before = copy.deepcopy(mission)
        archive_project(self.state, "p", NOW, [mission])
        self.assertEqual(mission, before)

    def test_foreign_project_dependency_blocks_project_removal_but_internal_one_does_not(self):
        self.state["tasks"].append({"id": "b", "project_id": "p", "title": "Inside", "status": "ready", "depends_on": ["a"]})
        self.state["tasks"].append({"id": "c", "project_id": "q", "title": "External dependency", "status": "done", "depends_on": ["b"]})
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "External dependency"):
            archive_project(self.state, "p", NOW)
        self.assertEqual(self.state, before)
        self.state["tasks"][-1]["deleted_at"] = NOW
        archive_project(self.state, "p", NOW)
        self.assertEqual(self.state["projects"][0]["deleted_at"], NOW)

    def test_project_hidden_as_a_whole_still_preserves_external_dependency_edges(self):
        self.state["projects"][1]["deleted_at"] = NOW
        self.state["tasks"].append({"id": "b", "project_id": "q", "title": "Hidden project dependent", "depends_on": ["a"]})
        self.assert_rejected_without_mutation(lambda: archive_project(self.state, "p", NOW))
        self.assert_rejected_without_mutation(lambda: archive_task(self.state, "a", NOW))

    def test_delete_and_restore_are_idempotent(self):
        archive_task(self.state, "a", NOW)
        before = copy.deepcopy(self.state)
        archive_task(self.state, "a", LATER)
        self.assertEqual(self.state, before)
        restore_task(self.state, "a", LATER)
        before = copy.deepcopy(self.state)
        restore_task(self.state, "a", NOW)
        self.assertEqual(self.state, before)
        archive_project(self.state, "p", NOW)
        before = copy.deepcopy(self.state)
        archive_project(self.state, "p", LATER)
        self.assertEqual(self.state, before)
        restore_project(self.state, "p", LATER)
        before = copy.deepcopy(self.state)
        restore_project(self.state, "p", NOW)
        self.assertEqual(self.state, before)

    def test_project_restore_rejects_live_project_using_the_resolved_path(self):
        archive_project(self.state, "p", NOW)
        self.state["projects"][1].update(name="Replacement project", path=str(Path("fixture-source").resolve()))
        before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, "Replacement project"):
            restore_project(self.state, "p", LATER)
        self.assertEqual(self.state, before)
        self.state["projects"][1]["deleted_at"] = NOW
        restore_project(self.state, "p", LATER)
        self.assertIsNone(self.state["projects"][0]["deleted_at"])

    def test_missing_records_and_invalid_timestamp_do_not_mutate_state(self):
        for action in (lambda: archive_task(self.state, "missing", NOW),
                       lambda: restore_task(self.state, "missing", NOW),
                       lambda: archive_project(self.state, "missing", NOW),
                       lambda: restore_project(self.state, "missing", NOW),
                       lambda: archive_task(self.state, "a", ""),
                       lambda: archive_project(self.state, "p", None)):
            self.assert_rejected_without_mutation(action)


if __name__ == "__main__":
    unittest.main()
