"""Workspace/chat/recycle-bin integration. Local fixtures only; no model calls."""
import copy
import json
import os
import sys
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener
from unittest.mock import patch

import test_server as _fixtures


class WorkspaceUXTests(unittest.TestCase):
    # Reuse fixture setup, never inherit/alias the original TestCase into this module.
    setUp = _fixtures.BoardTests.setUp
    tearDown = _fixtures.BoardTests.tearDown
    task = _fixtures.BoardTests.task

    def project(self, name="Second project"):
        folder = Path(self.tmp.name) / ("project-" + str(len(self.board.STATE["projects"])))
        folder.mkdir()
        return self.board.create_project({"name": name, "path": str(folder)})

    def mission(self):
        return self.board.create_autonomous_task({"title": "Offline delivery", "description": "Fixture only",
            "project_id": "test", "allowed_paths": ["sample.py"], "start": False,
            "policy": {"checks": [{"kind": "python_unittest", "modules": ["test_sample"]}]}})

    def reply(self, chat, message="Discuss an idea"):
        command = [sys.executable, "-c", "import sys; sys.stdin.read(); print('Offline discussion reply')"]
        with patch.object(self.board.threading, "Thread"), patch.object(self.board, "command_for", return_value=command):
            self.board.send_chat(chat["id"], {"message": message, "agent": "deepseek"})
            self.assertTrue(self.board.execute_chat(chat["id"], chat["turn_id"]))
        folder = self.board.DATA / "chats" / chat["id"] / chat["turn_id"]
        return folder, (folder / "prompt.txt").read_text(encoding="utf-8")

    @contextmanager
    def http(self):
        server = self.board.ThreadingHTTPServer(("127.0.0.1", 0), self.board.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = build_opener(ProxyHandler({}))

        def post(path, body=None):
            request = Request(f"http://127.0.0.1:{server.server_port}" + path,
                              data=json.dumps(body or {}).encode(), headers={"Content-Type": "application/json"})
            try:
                with opener.open(request, timeout=3) as response:
                    return response.status, json.load(response)
            except HTTPError as error:
                return error.code, json.load(error)
        try:
            yield post
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_free_discussion_accepts_omitted_null_and_empty_scope(self):
        for body in ({}, {"project_id": None}, {"project_id": ""}):
            with self.subTest(body=body):
                chat = self.board.create_chat({**body, "agent": "deepseek"})
                self.assertIsNone(chat["project_id"])
                self.assertFalse(chat["include_source"])
                self.assertFalse(chat["task_id"])
        context = self.board.chat_scope_project(None)
        self.assertIsNone(context["id"])
        self.assertEqual(context["path"], "")
        self.assertEqual(context["context_files"], [])
        self.assertEqual(context["context_urls"], [])

    def test_free_discussion_rejects_source_snapshot_or_project_task(self):
        task = self.task()
        before = copy.deepcopy(self.board.STATE.get("chats", []))
        with self.assertRaises(ValueError):
            self.board.create_chat({"project_id": None, "agent": "deepseek", "include_source": True})
        with self.assertRaises(ValueError):
            self.board.create_chat({"project_id": None, "agent": "deepseek", "task_id": task["id"]})
        self.assertEqual(self.board.STATE.get("chats", []), before)

    def test_free_local_executor_round_carries_history_without_other_project_context(self):
        marker = "PRIVATE_PROJECT_BRIEF_7301"
        brief = self.source / "brief.md"
        brief.write_text(marker, encoding="utf-8")
        self.board.update_project("test", {"context_files": [str(brief)]})
        task = self.task()
        task["description"] = "PRIVATE_TASK_SCOPE_5392"
        chat = self.board.create_chat({"agent": "deepseek"})
        self.reply(chat, "Remember the idea of a reading club")
        folder, prompt = self.reply(chat, "What was the idea?")
        self.assertEqual(chat["status"], "idle", chat.get("error"))
        self.assertEqual(len(chat["messages"]), 4)
        self.assertIn("Remember the idea of a reading club", prompt)
        self.assertNotIn(marker, prompt)
        self.assertNotIn("PRIVATE_TASK_SCOPE_5392", prompt)
        self.assertEqual(chat["context_sources"], [])
        briefing = json.loads((folder / "project-briefing.json").read_text(encoding="utf-8"))
        self.assertEqual(briefing["tasks"], [])
        self.assertEqual(briefing["task_count"], 0)
        self.assertEqual((self.source / "sample.py").read_text(), "value = 1\n")

    def test_scope_change_keeps_history_clears_old_links_and_invalidates_consensus(self):
        task = self.task()
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek", "task_id": task["id"], "include_source": True})
        chat.update(messages=[{"role": "user", "text": "Carry this idea"}], consensus="Keep the reading-club idea",
                    context_sources=[{"source": "old-fixture"}], context_read_at="old-time")
        old_messages = copy.deepcopy(chat["messages"])
        project = self.project()
        self.board.link_chat_project(chat["id"], {"project_id": project["id"]})
        self.assertEqual(chat["project_id"], project["id"])
        self.assertFalse(chat["task_id"])
        self.assertFalse(chat["include_source"])
        self.assertEqual(chat["context_sources"], [])
        self.assertFalse(chat["context_read_at"])
        self.assertEqual(chat["messages"][:len(old_messages)], old_messages)
        self.assertEqual(chat["consensus"], "Keep the reading-club idea")
        self.assertTrue(chat["consensus_needs_review"])
        self.assertTrue(chat["scope_history"])
        self.board.link_chat_project(chat["id"], {"project_id": None})
        self.assertIsNone(chat["project_id"])
        self.assertEqual(chat["messages"][:len(old_messages)], old_messages)

    def test_next_scope_round_refreshes_only_the_new_project_references(self):
        marker_a, marker_b = "OLD_AUTOMATIC_REFERENCE_4701", "NEW_AUTOMATIC_REFERENCE_9274"
        brief_a = self.source / "brief-a.md"
        brief_a.write_text(marker_a, encoding="utf-8")
        self.board.update_project("test", {"context_files": [str(brief_a)]})
        project = self.project()
        brief_b = Path(project["path"]) / "brief-b.md"
        brief_b.write_text(marker_b, encoding="utf-8")
        self.board.update_project(project["id"], {"context_files": [str(brief_b)]})
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek"})
        _, first = self.reply(chat, "Read the attached context")
        self.assertIn(marker_a, first)
        self.board.link_chat_project(chat["id"], {"project_id": project["id"]})
        _, second = self.reply(chat, "Now discuss this project")
        self.assertIn(marker_b, second)
        self.assertNotIn(marker_a, second)
        self.assertEqual(len([m for m in chat["messages"] if m["role"] in ("user", "assistant")]), 4)

    def test_running_scope_change_and_deleted_target_are_rejected_without_mutation(self):
        chat = self.board.create_chat({"agent": "deepseek"})
        project = self.project()
        chat["status"] = "running"
        before = copy.deepcopy(chat)
        with self.assertRaises(ValueError):
            self.board.link_chat_project(chat["id"], {"project_id": project["id"]})
        self.assertEqual(chat, before)
        chat["status"] = "idle"
        self.board.archive_record("project", project["id"])
        before = copy.deepcopy(chat)
        with self.assertRaises(ValueError):
            self.board.link_chat_project(chat["id"], {"project_id": project["id"]})
        self.assertEqual(chat, before)

    def test_scope_selection_of_current_project_does_not_discard_links(self):
        task = self.task()
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek", "task_id": task["id"], "include_source": True})
        chat["consensus"] = "Current agreed scope"
        before = copy.deepcopy(chat)
        self.board.link_chat_project(chat["id"], {"project_id": "test"})
        self.assertEqual(chat, before)

    def test_old_task_does_not_inherit_consensus_after_discussion_moves_projects(self):
        task = self.task()
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek", "task_id": task["id"]})
        task["discussion_id"] = chat["id"]
        project = self.project()
        self.board.link_chat_project(chat["id"], {"project_id": project["id"]})
        chat["consensus"] = "NEW_PROJECT_ONLY_CONSENSUS_8624"
        chat["messages"] = [{"role": "assistant", "text": "NEW_PROJECT_ONLY_REPLY_5149"}]
        context = self.board.discussion_context(task)
        self.assertNotIn("NEW_PROJECT_ONLY_CONSENSUS_8624", context)
        self.assertNotIn("NEW_PROJECT_ONLY_REPLY_5149", context)

    def test_historical_discussion_keeps_old_task_editable_without_relinking_new_tasks(self):
        task = self.task()
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek", "task_id": task["id"]})
        task["discussion_id"] = chat["id"]
        project = self.project()
        self.board.link_chat_project(chat["id"], {"project_id": project["id"]})
        chat["consensus"] = "OTHER_SCOPE_NEW_CONSENSUS_3519"
        chat["messages"] = [{"role": "assistant", "text": "OTHER_SCOPE_NEW_MESSAGE_5391"}]
        other_chat = self.board.create_chat({"project_id": project["id"], "agent": "deepseek"})
        payload = {"title": "New unrelated card", "description": "Keep this in the first project",
                   "project_id": "test", "agent": "deepseek", "mode": "implement",
                   "allowed_paths": ["sample.py"], "limit_minutes": 1}
        with self.http() as post:
            for body in ({"title": "Edit without discussion field"},
                         {"title": "Edit with historical discussion", "discussion_id": chat["id"]}):
                with self.subTest(body=body):
                    status, response = post(f"/api/tasks/{task['id']}/update", body)
                    self.assertEqual(status, 200, response)
                    self.assertEqual(task["title"], body["title"])
                    self.assertEqual(task["discussion_id"], chat["id"])
                    self.assertEqual(task["project_id"], "test")
            before = copy.deepcopy(self.board.STATE)
            status, _ = post("/api/tasks", {**payload, "discussion_id": chat["id"]})
            self.assertEqual(status, 400)
            status, _ = post(f"/api/tasks/{task['id']}/update", {"discussion_id": other_chat["id"]})
            self.assertEqual(status, 400)
            self.assertEqual(self.board.STATE, before)
            status, response = post("/api/tasks", payload)
            self.assertEqual(status, 200, response)
            new_task = self.board.find_task(response["data"]["id"])
        self.assertFalse(new_task["discussion_id"])
        for candidate in (task, new_task):
            context = self.board.discussion_context(candidate)
            self.assertNotIn("OTHER_SCOPE_NEW_CONSENSUS_3519", context)
            self.assertNotIn("OTHER_SCOPE_NEW_MESSAGE_5391", context)

    def test_explicit_new_directory_project_creation_is_opt_in_and_preserves_existing_files(self):
        target = Path(self.tmp.name) / "new-workspace"
        with self.assertRaises(ValueError):
            self.board.create_project({"name": "New", "path": str(target)})
        self.assertFalse(target.exists())
        project = self.board.create_project({"name": "New", "path": str(target), "create_directory": True})
        self.assertTrue(target.is_dir())
        self.assertEqual(Path(project["path"]), target)
        marker = target / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        count = len(self.board.STATE["projects"])
        with self.assertRaises(ValueError):
            self.board.create_project({"name": "Existing", "path": str(target), "create_directory": True})
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(len(self.board.STATE["projects"]), count)

    def test_directory_creation_rejects_invalid_metadata_before_creating_a_folder(self):
        target = Path(self.tmp.name) / "must-not-be-created"
        for changes in ({"name": ""}, {"check": "invalid-check"}, {"create_directory": "true"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.board.create_project({"name": "New", "path": str(target), "create_directory": True, **changes})
            self.assertFalse(target.exists())

    def test_explicit_folder_creation_requires_absolute_path_and_refuses_files(self):
        previous = Path.cwd()
        try:
            os.chdir(self.tmp.name)
            with self.assertRaises(ValueError):
                self.board.create_project({"name": "Relative", "path": "relative-new", "create_directory": True})
            self.assertFalse((Path(self.tmp.name) / "relative-new").exists())
        finally:
            os.chdir(previous)
        file = Path(self.tmp.name) / "existing-file"
        file.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.board.create_project({"name": "File", "path": str(file), "create_directory": True})
        self.assertEqual(file.read_text(), "keep")

    def test_task_recycle_bin_hides_card_keeps_records_and_restores_without_auto_start(self):
        task = self.task()
        task["auto_start"] = True
        self.board.archive_record("task", task["id"])
        public = self.board.public_state()
        self.assertNotIn(task["id"], {item["id"] for item in public["tasks"]})
        self.assertIn(task["id"], {item["id"] for item in public["trash"]["tasks"]})
        self.assertIs(self.board.find_task(task["id"]), task)
        self.board.archive_record("task", task["id"], restore=True)
        self.assertIn(task["id"], {item["id"] for item in self.board.public_state()["tasks"]})
        self.assertFalse(task["auto_start"])
        self.assertEqual((self.source / "sample.py").read_text(), "value = 1\n")

    def test_project_recycle_bin_hides_views_but_keeps_history_and_individual_task_deletions(self):
        task = self.task()
        separately_deleted = self.task()
        self.board.archive_record("task", separately_deleted["id"])
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek"})
        chat["messages"] = [{"role": "user", "text": "Keep original history"}]
        self.board.archive_record("project", "test")
        public = self.board.public_state()
        self.assertNotIn("test", {item["id"] for item in public["projects"]})
        self.assertNotIn(task["id"], {item["id"] for item in public["tasks"]})
        self.assertNotIn(chat["id"], {item["id"] for item in public["chats"]})
        self.assertIn("test", {item["id"] for item in public["trash"]["projects"]})
        self.assertEqual(self.board.find_chat(chat["id"])["messages"], [{"role": "user", "text": "Keep original history"}])
        self.board.archive_record("project", "test", restore=True)
        self.assertIn(task["id"], {item["id"] for item in self.board.public_state()["tasks"]})
        self.assertNotIn(separately_deleted["id"], {item["id"] for item in self.board.public_state()["tasks"]})
        self.assertTrue(self.board.find_task(separately_deleted["id"])["deleted_at"])

    def test_archived_autonomous_delivery_keeps_durable_record_and_is_not_schedulable(self):
        mission = self.mission()
        service = self.board.autonomy_service()
        self.board.archive_record("task", mission["task_id"])
        self.assertEqual(service.store.get(mission["id"])["phase"], "paused")
        self.assertNotIn(mission["id"], {m["id"] for m in self.board.public_state()["autonomy"]["missions"]})
        self.assertFalse(service.runtime.ready(mission))
        self.board.archive_record("task", mission["task_id"], restore=True)
        self.assertTrue(service.runtime.ready(mission))
        self.assertEqual(service.store.get(mission["id"])["phase"], "paused")

    def test_archived_task_and_project_cannot_launch_models_or_old_chats(self):
        task = self.task()
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek"})
        self.board.archive_record("task", task["id"])
        with patch.object(self.board.threading, "Thread") as thread:
            with self.assertRaises(ValueError):
                self.board.start_task(task["id"])
            thread.assert_not_called()
        self.board.archive_record("project", "test")
        with patch.object(self.board.threading, "Thread") as thread:
            with self.assertRaises(ValueError):
                self.board.send_chat(chat["id"], {"message": "Do not run", "agent": "deepseek"})
            thread.assert_not_called()

    def test_scheduler_and_briefing_do_not_reintroduce_deleted_cards(self):
        task = self.task()
        task.update(auto_start=True, description="ARCHIVED_CARD_CONTENT_1894")
        self.board.archive_record("task", task["id"])
        task["auto_start"] = True  # A stale legacy preference must not bypass archive guards.
        with patch.object(self.board, "start_task") as start:
            self.board.maybe_start_next()
            start.assert_not_called()
        briefing = self.board.project_briefing(self.board.find_project("test"))
        self.assertEqual(briefing["task_count"], 0)
        self.assertNotIn("ARCHIVED_CARD_CONTENT_1894", briefing["prompt"])

    def test_http_deleted_mission_cannot_resume_and_card_can_restore(self):
        mission = self.mission()
        with self.http() as post:
            status, _ = post(f"/api/tasks/{mission['task_id']}/delete")
            self.assertEqual(status, 200)
            status, _ = post(f"/api/missions/{mission['id']}/resume")
            self.assertEqual(status, 400)
            self.assertEqual(self.board.autonomy_service().store.get(mission["id"])["phase"], "paused")
            status, _ = post(f"/api/tasks/{mission['task_id']}/restore")
            self.assertEqual(status, 200)

    def test_restore_project_rejects_reused_source_folder_without_mutation(self):
        self.board.archive_record("project", "test")
        replacement = self.board.create_project({"name": "Replacement workspace", "path": str(self.source)})
        before = copy.deepcopy(self.board.STATE)
        with self.assertRaisesRegex(ValueError, "Replacement workspace"):
            self.board.archive_record("project", "test", restore=True)
        self.assertEqual(self.board.STATE, before)
        self.assertTrue(self.board.find_project("test")["deleted_at"])
        self.assertFalse(self.board.find_project(replacement["id"]).get("deleted_at"))
        self.assertEqual((self.source / "sample.py").read_text(), "value = 1\n")

    def test_http_project_delete_restore_and_chat_scope_routes(self):
        chat = self.board.create_chat({"agent": "deepseek"})
        with self.http() as post:
            status, _ = post(f"/api/chats/{chat['id']}/project", {"project_id": "test"})
            self.assertEqual(status, 200)
            self.assertEqual(chat["project_id"], "test")
            status, _ = post("/api/projects/test/delete")
            self.assertEqual(status, 200)
            status, _ = post("/api/projects/test/restore")
            self.assertEqual(status, 200)
            status, _ = post(f"/api/chats/{chat['id']}/project", {"project_id": None})
            self.assertEqual(status, 200)
            self.assertIsNone(chat["project_id"])


if __name__ == "__main__":
    unittest.main()
