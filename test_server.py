"""Offline checks: no Codex / DeepSeek calls and no Unity Editor launch."""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class BoardTests(unittest.TestCase):
    def setUp(self):
        child_encoding = patch.dict(os.environ, {"PYTHONUTF8": "1"})
        child_encoding.start()
        self.addCleanup(child_encoding.stop)
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        with patch.dict(os.environ, {"AGENTBOARD_DATA_DIR": str(root / "data"),
                                      "AGENTBOARD_WORKSPACES_DIR": str(root / "workspaces"),
                                      "AGENTBOARD_TEST_MODE": "1"}):
            spec = importlib.util.spec_from_file_location("test_board_module", Path(__file__).with_name("server.py"))
            self.board = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.board)
        # Mock only the board's scheduler. Windows subprocess.communicate uses
        # the real threading module internally to drain pipes.
        self.board.threading = SimpleNamespace(**vars(self.board.threading))
        self.source = root / "source"
        self.source.mkdir()
        (self.source / "sample.py").write_text("value = 1\n", encoding="utf-8")
        self.protected = root / "protected"
        self.protected.mkdir()
        (self.protected / "save.json").write_text("original", encoding="utf-8")
        self.board.STATE = {"version": 1, "projects": [{"id": "test", "name": "测试",
            "path": str(self.source), "protected_paths": [str(self.protected)],
            "context_files": [], "check": "python_compile"}], "tasks": [], "runs": [],
            "budget": {"codex_5h_remaining": None, "observed_at": None}}
        self.board.save()

    def tearDown(self):
        self.tmp.cleanup()

    def task(self, patterns=None):
        return self.board.create_task({"title": "修改样例", "description": "修改 sample.py",
            "project_id": "test", "agent": "deepseek", "mode": "implement",
            "allowed_paths": patterns or ["sample.py"], "limit_minutes": 1})

    def test_first_run_has_no_personal_projects(self):
        self.assertEqual(self.board.initial_state()["projects"], [])
        self.assertEqual(self.board.initial_state()["chats"], [])

    def test_autonomous_task_is_linked_and_does_not_invoke_model_when_saved(self):
        mission = self.board.create_autonomous_task({"title": "自主验收", "description": "修改sample",
            "project_id": "test", "allowed_paths": ["sample.py"], "start": False,
            "policy": {"checks": [{"kind": "python_unittest", "modules": ["test_sample"]}]}})
        self.assertEqual(mission["phase"], "paused")
        task = self.board.find_task(mission["task_id"])
        self.assertEqual(task["agent"], "codex")
        self.assertFalse(task["fallback_to_deepseek"])
        self.assertEqual(task["mission_id"], mission["id"])
        self.assertEqual(task["run_ids"], [mission["id"]])
        service = self.board.autonomy_service()
        service.runtime.attach(service.store.get(mission["id"]))
        self.assertEqual(task["run_ids"], [mission["id"]])
        self.assertEqual(len(self.board.STATE["runs"]), 1)
        self.assertFalse(service.status()["running"])

    def test_recovery_does_not_rebaseline_tampered_delivered_workspace(self):
        mission = self.board.create_autonomous_task({"title": "自主验收", "description": "修改sample",
            "project_id": "test", "allowed_paths": ["sample.py"], "start": False,
            "policy": {"checks": [{"kind": "python_unittest", "modules": ["test_sample"]}]}})
        service = self.board.autonomy_service()
        prepared = service.runtime.prepare(mission)
        workspace = Path(prepared["workspace"])
        (workspace / "sample.py").write_text("value = 2\n", encoding="utf-8")
        mission = service.store.update(mission["id"], {**prepared,
            "checks": [{"name": "offline fixture", "passed": True, "tests": 1, "detail": "fixture"}],
            "review_result": {"verdict": "pass", "summary": "offline fixture", "findings": []}})
        receipt = service.runtime.receipt(mission, service.runtime.integrity(mission))
        checkpoint = service.runtime.workspace_snapshot(mission)
        service.change(mission["id"], {"phase": "review", "receipt": receipt, "workspace_after": checkpoint}, "fixture", "offline fixture")
        (workspace / "sample.py").write_text("value = 999\n", encoding="utf-8")
        service._recover()
        with self.assertRaisesRegex(ValueError, "隔离工作区"):
            self.board.accept_task(mission["task_id"])
        self.assertEqual((self.source / "sample.py").read_text(encoding="utf-8"), "value = 1\n")

    def test_import_does_not_normalize_or_write_existing_live_state(self):
        state_path = self.board.STATE_FILE
        before = state_path.read_bytes()
        with patch.dict(os.environ, {"AGENTBOARD_DATA_DIR": str(self.board.DATA),
                                    "AGENTBOARD_WORKSPACES_DIR": str(self.board.WORKSPACES), "AGENTBOARD_TEST_MODE": "1"}):
            spec = importlib.util.spec_from_file_location("second_readonly_import", Path(__file__).with_name("server.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.assertEqual(state_path.read_bytes(), before)

    def test_model_override_snapshot_keeps_guards_and_does_not_follow_edits(self):
        from model_settings import ModelSettings
        import json
        home = Path(self.tmp.name) / "codex"
        home.mkdir()
        (home / "models_cache.json").write_text(json.dumps({"models": [{"slug": "fixture", "visibility": "list", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}]}]}), encoding="utf-8")
        self.board.MODELS = ModelSettings(self.board.DATA, home)
        self.board.MODELS.save({"model": "fixture", "reasoning_effort": "low"})
        task = self.board.create_task({"title": "fixture", "description": "offline", "project_id": "test", "agent": "codex", "mode": "explore", "fallback_to_deepseek": False, "model_options": {"reasoning_effort": "high"}})
        self.board.STATE["budget"].update(codex_5h_remaining=90, observed_at=self.board.now())
        with patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
        self.assertEqual(run["execution_config"], {"model": "fixture", "reasoning_effort": "high"})
        self.board.MODELS.save({})
        self.board.TEST_MODE = False  # Inspect argument construction only; no subprocess.
        with patch.object(self.board.shutil, "which", return_value="codex"):
            cmd = self.board.command_for({**task, "execution_config": run["execution_config"]}, self.source, self.board.DATA)
        self.assertIn('--model', cmd)
        self.assertIn('model_reasoning_effort="high"', cmd)
        self.assertIn('sandbox_workspace_write.network_access=false', cmd)
        self.assertIn('approval_policy=never', cmd)

    def test_quota_fallback_does_not_pass_codex_model_to_deepseek(self):
        task = self.task()
        task.update(agent="codex", model_options={"model": "unavailable-after-fallback"})
        with patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
        self.assertEqual(run["agent"], "deepseek")
        self.assertEqual(run["execution_config"], {})

    def test_model_settings_are_blocked_during_tasks_and_group_batches(self):
        self.board.STATE["runs"] = [{"agent": "codex", "status": "preparing"}]
        with self.assertRaises(ValueError):
            self.board.save_model_settings({})
        self.board.STATE["runs"] = []
        self.board.STATE["chats"] = [{"agent": "deepseek", "members": ["codex", "deepseek"], "status": "running"}]
        with self.assertRaises(ValueError):
            self.board.save_model_settings({})
        self.board.STATE["chats"] = []
        self.assertEqual(self.board.save_model_settings({})["codex"]["preferences"], {"model": "", "reasoning_effort": ""})

    def test_http_page_works_without_console_error_stream(self):
        from urllib.request import urlopen
        server = self.board.ThreadingHTTPServer(("127.0.0.1", 0), self.board.Handler)
        thread = self.board.threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(self.board.sys, "stderr", None):
                for path in ("/", "/static/appearance.js"):
                    with urlopen(f"http://127.0.0.1:{server.server_port}{path}", timeout=3) as response:
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_board_runtime_data_is_not_copied_as_project_source(self):
        runtime = self.source / "private-runtime"
        runtime.mkdir()
        (runtime / "agents.json").write_text('private-config', encoding='utf-8')
        workspace = Path(self.tmp.name) / "source-copy"
        with patch.object(self.board, "DATA", runtime):
            self.assertNotIn("private-runtime/agents.json", self.board.inventory(self.source))
            self.board.copy_source(self.board.find_project("test"), workspace)
        self.assertFalse((workspace / "private-runtime").exists())

    def add_simulator(self, agent="local-sim"):
        return self.board.save_agent({"id": agent, "name": "Local simulator", "kind": "mock"})

    def test_simulator_task_runs_without_accounts_and_is_marked(self):
        self.add_simulator()
        task = self.board.create_task({"title": "Simulation", "description": "Read-only rehearsal", "project_id": "test", "agent": "local-sim", "mode": "explore"})
        with patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
        self.board.execute_run(run["id"])
        result = self.board.find_run(run["id"])
        self.assertEqual(result["status"], "review", result.get("error"))
        self.assertTrue(result["simulation"])
        self.assertEqual((self.source / "sample.py").read_text(), "value = 1\n")

    def test_custom_group_directing_and_shared_broadcast(self):
        self.add_simulator("sim-one")
        self.add_simulator("sim-two")
        chat = self.board.create_chat({"project_id": "test", "agent": "sim-one", "mode": "group", "members": ["sim-one", "sim-two"]})
        with patch.object(self.board.threading, "Thread"):
            self.board.send_chat(chat["id"], {"message": "/sim-two Hello", "agent": "all"})
        self.board.execute_group_chat(chat["id"], chat["turn_id"])
        replies = [m for m in chat["messages"] if m["role"] == "assistant"]
        self.assertEqual([m["agent"] for m in replies], ["sim-two"])
        self.assertTrue(replies[0]["simulation"])
        with patch.object(self.board.threading, "Thread"):
            self.board.send_chat(chat["id"], {"message": "Hello everyone", "agent": "all"})
        self.board.execute_group_chat(chat["id"], chat["turn_id"])
        replies = [m for m in chat["messages"] if m["role"] == "assistant"]
        self.assertEqual([m["agent"] for m in replies], ["sim-two", "sim-one", "sim-two"])

    def test_agent_config_cannot_change_while_in_use(self):
        self.add_simulator()
        chat = self.board.create_chat({"project_id": "test", "agent": "local-sim"})
        with patch.object(self.board.threading, "Thread"):
            self.board.send_chat(chat["id"], {"message": "Hello"})
        with self.assertRaises(ValueError):
            self.board.save_agent({"id": "local-sim", "name": "Changed", "kind": "mock", "enabled": False})

    def test_api_and_simulator_cannot_be_used_for_implementation(self):
        self.add_simulator()
        for agent in ("local-sim", "api-agent"):
            if agent == "api-agent":
                self.board.save_agent({"id": agent, "name": "API", "kind": "api", "endpoint": "https://provider.example/v1/chat/completions", "model": "sample", "key_env": "TEST_AGENT_KEY"})
            with self.assertRaises(ValueError):
                self.board.create_task({"title": "No edits", "description": "No", "project_id": "test", "agent": agent, "mode": "implement", "allowed_paths": ["sample.py"]})

    def test_cli_adapter_uses_existing_scope_checks(self):
        self.board.save_agent({"id": "local-cli", "name": "Local CLI", "kind": "cli", "executable": sys.executable, "args": ["-c", "from pathlib import Path; Path('outside.txt').write_text('no'); print('AGENTBOARD_STATUS: DONE')"], "can_implement": True})
        task = self.board.create_task({"title": "Scope", "description": "Test scope", "project_id": "test", "agent": "local-cli", "mode": "implement", "allowed_paths": ["sample.py"]})
        with patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
        # Only allow this deliberately constructed local Python fixture, not real models.
        command = self.board.REGISTRY.command("local-cli", self.source, self.source / "answer.txt")
        with patch.object(self.board, "command_for", return_value=command):
            self.board.execute_run(run["id"])
        self.assertEqual(self.board.find_run(run["id"])["status"], "blocked")
        self.assertFalse((self.source / "outside.txt").exists())

    def test_disabled_agent_and_too_large_room_are_rejected(self):
        self.add_simulator()
        self.board.save_agent({"id": "local-sim", "name": "Disabled", "kind": "mock", "enabled": False})
        with self.assertRaises(ValueError):
            self.board.create_chat({"project_id": "test", "agent": "local-sim"})
        with self.assertRaises(ValueError):
            self.board.create_chat({"project_id": "test", "mode": "group", "members": ["codex"] * 7})

    def test_deepseek_profile_is_configurable_without_launching(self):
        with patch.object(self.board, "TEST_MODE", False), patch.dict(os.environ, {"AGENTBOARD_DEEPSEEK_PROFILE": "my-headless"}), patch.object(self.board.shutil, "which", return_value="dsh"):
            command = self.board.command_for({"agent": "deepseek"}, self.source, Path(self.tmp.name))
        self.assertEqual(command[1:], ["--profile", "my-headless", "-"])

    def test_unity_check_reads_project_editor_version(self):
        settings = self.source / "ProjectSettings"
        settings.mkdir()
        (settings / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.9.1f1\n", encoding="utf-8")
        from types import SimpleNamespace
        with patch.object(self.board.shutil, "which", return_value="unity"), patch.object(self.board.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            passed, _ = self.board.run_checks({"check": "unity_compile"}, self.source, Path(self.tmp.name))
        self.assertTrue(passed)
        self.assertIn("6000.9.1f1", run.call_args.args[0])

    def test_demo_http_rejects_mutating_requests(self):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        server = self.board.ThreadingHTTPServer(("127.0.0.1", 0), self.board.Handler)
        thread = self.board.threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(self.board, "DEMO_MODE", True), patch.object(self.board, "create_task") as create:
                request = Request(f"http://127.0.0.1:{server.server_port}/api/tasks", data=b"{}", headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request)
                self.assertEqual(caught.exception.code, 400)
                create.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_scope_and_parent_escape(self):
        self.assertTrue(self.board.allowed("Assets/Scripts/UI/a.cs", ["Assets/Scripts/UI/**"]))
        self.assertFalse(self.board.allowed("Assets/Scripts/World/a.cs", ["Assets/Scripts/UI/**"]))
        with self.assertRaises(ValueError):
            self.board.valid_patterns(["../Saves/*"])
        with self.assertRaises(ValueError):
            self.board.valid_patterns(["C:/Users/*"])

    def test_allowed_change_can_be_promoted_without_agent(self):
        task = self.task()
        command = [sys.executable, "-c", "from pathlib import Path; Path('sample.py').write_text('value = 2\\n'); print('AGENTBOARD_STATUS: DONE')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread") as fake_thread:
            run = self.board.start_task(task["id"])["run"]
            fake_thread.assert_called_once()
            self.board.execute_run(run["id"])
        self.assertEqual(self.board.find_run(run["id"])["status"], "review")
        self.assertTrue(self.board.find_run(run["id"])["automated_check_passed"])
        self.assertEqual((self.source / "sample.py").read_text(), "value = 1\n")
        self.board.accept_task(task["id"])
        self.assertEqual((self.source / "sample.py").read_text(), "value = 2\n")
        self.assertEqual((self.protected / "save.json").read_text(), "original")

    def test_out_of_scope_change_is_blocked(self):
        task = self.task()
        command = [sys.executable, "-c", "from pathlib import Path; Path('bad.py').write_text('x=1'); print('AGENTBOARD_STATUS: DONE')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
            self.board.execute_run(run["id"])
        self.assertEqual(self.board.find_task(task["id"])["status"], "blocked")
        self.assertFalse((self.source / "bad.py").exists())

    def test_source_drift_prevents_promotion(self):
        task = self.task()
        command = [sys.executable, "-c", "from pathlib import Path; Path('sample.py').write_text('value = 2\\n'); print('AGENTBOARD_STATUS: DONE')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
            self.board.execute_run(run["id"])
        (self.source / "sample.py").write_text("value = 99\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.board.accept_task(task["id"])
        self.assertEqual((self.source / "sample.py").read_text(), "value = 99\n")

    def test_protected_save_change_blocks_run(self):
        task = self.task()
        code = f"from pathlib import Path; Path({str(self.protected / 'save.json')!r}).write_text('changed'); print('AGENTBOARD_STATUS: DONE')"
        with patch.object(self.board, "command_for", return_value=[sys.executable, "-c", code]), patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
            self.board.execute_run(run["id"])
        self.assertEqual(self.board.find_task(task["id"])["status"], "blocked")
        self.assertIn("受保护", self.board.find_run(run["id"])["error"])

    def test_weekly_only_quota_allows_codex_tasks_and_chat(self):
        from usage_probe import summarize_rate_limits
        self.board.STATE["budget"] = summarize_rate_limits({"ordinaryUsageAllowed": True,
            "rateLimits": {"primary": {"windowDurationMins": 10080, "usedPercent": 23}}})
        task = self.board.create_task({"title": "weekly account", "description": "offline",
            "project_id": "test", "agent": "codex", "mode": "explore", "fallback_to_deepseek": False})
        with patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
        self.assertEqual(run["agent"], "codex")
        self.assertEqual(run["budget_note"], "")
        self.board.guard_codex_chat_budget()
        self.board.STATE["budget"]["quota_windows"][0]["remaining_percent"] = 15
        with self.assertRaises(ValueError):
            self.board.guard_codex_chat_budget()

    def test_low_codex_budget_falls_back_without_starting_codex(self):
        self.board.STATE["budget"] = {"codex_5h_remaining": 15, "observed_at": self.board.now()}
        task = self.board.create_task({"title": "调查", "description": "只读调查",
            "project_id": "test", "agent": "codex", "mode": "explore", "limit_minutes": 1})
        with patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
        self.assertEqual(run["agent"], "deepseek")
        self.assertIn("15%", run["budget_note"])

    def test_assertions_block_false_completion(self):
        task = self.board.create_task({"title": "规则检查", "description": "修改样例",
            "project_id": "test", "agent": "deepseek", "mode": "implement",
            "allowed_paths": ["sample.py"], "assertions": ["contains:sample.py | value = 3"],
            "limit_minutes": 1})
        command = [sys.executable, "-c", "from pathlib import Path; Path('sample.py').write_text('value = 2\\n'); print('AGENTBOARD_STATUS: DONE')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
            self.board.execute_run(run["id"])
        actual = self.board.find_run(run["id"])
        self.assertEqual(actual["status"], "blocked")
        self.assertFalse(actual["assertion_results"][0]["passed"])
        self.assertTrue((self.board.RUNS / run["id"] / "capsule.md").is_file())

    def test_rollback_restores_original_and_rejects_newer_edit(self):
        task = self.task()
        command = [sys.executable, "-c", "from pathlib import Path; Path('sample.py').write_text('value = 2\\n'); print('AGENTBOARD_STATUS: DONE')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
            self.board.execute_run(run["id"])
        self.board.accept_task(task["id"])
        (self.source / "sample.py").write_text("value = 9\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.board.rollback_task(task["id"])
        self.assertEqual((self.source / "sample.py").read_text(), "value = 9\n")
        (self.source / "sample.py").write_text("value = 2\n", encoding="utf-8")
        self.board.rollback_task(task["id"])
        self.assertEqual((self.source / "sample.py").read_text(), "value = 1\n")
        self.assertEqual(self.board.find_task(task["id"])["status"], "ready")

    def test_question_enters_decision_inbox(self):
        task = self.board.create_task({"title": "需要决定", "description": "调查路线",
            "project_id": "test", "agent": "deepseek", "mode": "explore", "limit_minutes": 1})
        command = [sys.executable, "-c", "print('AGENTBOARD_QUESTION: 选哪种路线？\\nAGENTBOARD_OPTION: A\\nAGENTBOARD_OPTION: B\\nAGENTBOARD_STATUS: BLOCKED')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread"):
            run = self.board.start_task(task["id"])["run"]
            self.board.execute_run(run["id"])
        self.assertEqual(self.board.find_task(task["id"])["status"], "decision")
        self.assertEqual(self.board.find_run(run["id"])["decision"]["options"], ["A", "B"])

    def test_chat_preserves_history_without_creating_tasks(self):
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek"})
        command = [sys.executable, "-c", "import sys; sys.stdin.read(); print('Remembered: BLUE')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread"):
            self.board.send_chat(chat["id"], {"message": "Remember BLUE", "agent": "deepseek"})
            self.board.execute_chat(chat["id"], chat["turn_id"])
            self.assertEqual(chat["status"], "idle")
            self.board.send_chat(chat["id"], {"message": "What did I say?", "agent": "deepseek"})
            self.board.execute_chat(chat["id"], chat["turn_id"])
        self.assertEqual(len(chat["messages"]), 4)
        prompt = (self.board.DATA / "chats" / chat["id"] / chat["turn_id"] / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("Remember BLUE", prompt)
        self.assertIn("Remembered: BLUE", prompt)
        self.assertEqual(self.board.STATE["tasks"], [])
        self.assertEqual((self.source / "sample.py").read_text(), "value = 1\n")

    def test_chat_blocks_writes_in_source_snapshot(self):
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek", "include_source": True})
        command = [sys.executable, "-c", "from pathlib import Path; Path('sample.py').write_text('value=3'); print('ok')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread"):
            self.board.send_chat(chat["id"], {"message": "Read the source", "agent": "deepseek"})
            self.board.execute_chat(chat["id"], chat["turn_id"])
        self.assertEqual(chat["status"], "error")
        self.assertIn("文件改动", chat["error"])
        self.assertEqual(len(chat["messages"]), 1)
        self.assertEqual((self.source / "sample.py").read_text(), "value = 1\n")

    def test_chat_budget_and_stop_before_launch(self):
        chat = self.board.create_chat({"project_id": "test", "agent": "codex"})
        self.board.STATE["budget"] = {"codex_5h_remaining": 15, "observed_at": self.board.now()}
        with self.assertRaises(ValueError):
            self.board.send_chat(chat["id"], {"message": "Hello", "agent": "codex"})
        self.assertEqual(chat["messages"], [])
        with patch.object(self.board.threading, "Thread"), patch.object(self.board, "command_for") as command:
            self.board.send_chat(chat["id"], {"message": "Hello", "agent": "deepseek"})
            self.board.stop_chat(chat["id"])
            self.board.execute_chat(chat["id"], chat["turn_id"])
            command.assert_not_called()
        self.assertEqual(chat["status"], "error")

    def test_linked_task_chat_loads_latest_log_without_source_copy(self):
        log = Path(self.tmp.name) / "开发日志.md"
        log.write_text("LOG_VERSION_ONE", encoding="utf-8")
        self.board.update_project("test", {"context_files": [str(log)]})
        task = self.task()
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek", "task_id": task["id"]})
        command = [sys.executable, "-c", "import sys; sys.stdin.read(); print('Proposed plan')"]
        with patch.object(self.board, "command_for", return_value=command), patch.object(self.board.threading, "Thread"):
            self.board.send_chat(chat["id"], {"message": "Read current log", "agent": "deepseek"})
            self.board.execute_chat(chat["id"], chat["turn_id"])
            first_prompt = (self.board.DATA / "chats" / chat["id"] / chat["turn_id"] / "prompt.txt").read_text(encoding="utf-8")
            self.assertIn("LOG_VERSION_ONE", first_prompt)
            log.write_text("LOG_VERSION_TWO", encoding="utf-8")
            self.board.send_chat(chat["id"], {"message": "Read again", "agent": "deepseek"})
            self.board.execute_chat(chat["id"], chat["turn_id"])
        last_prompt = (self.board.DATA / "chats" / chat["id"] / chat["turn_id"] / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("LOG_VERSION_TWO", last_prompt)
        self.assertNotIn("LOG_VERSION_ONE", last_prompt)
        self.assertEqual(len(chat["context_sources"]), 1)
        self.assertEqual(task["status"], "ready")
        self.board.save_chat_consensus(chat["id"], {"consensus": "Keep save compatibility"})
        task["discussion_id"] = chat["id"]
        self.assertIn("Keep save compatibility", self.board.prompt_for(task))

    def test_missing_linked_log_blocks_before_launch(self):
        log = Path(self.tmp.name) / "handoff.md"
        log.write_text("CURRENT", encoding="utf-8")
        self.board.update_project("test", {"context_files": [str(log)]})
        task = self.task()
        log.unlink()
        with patch.object(self.board.threading, "Thread"), patch.object(self.board, "command_for") as command:
            run = self.board.start_task(task["id"])["run"]
            self.board.execute_run(run["id"])
            command.assert_not_called()
        self.assertEqual(self.board.find_task(task["id"])["status"], "blocked")
        self.assertIn("关联资料不存在", self.board.find_run(run["id"])["error"])

    def test_task_context_and_consensus_survive_task_update(self):
        log = Path(self.tmp.name) / "task-notes.md"
        log.write_text("TASK_SPECIFIC_REFERENCE", encoding="utf-8")
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek"})
        self.board.save_chat_consensus(chat["id"], {"consensus": "APPROVED_SCOPE"})
        task = self.board.create_task({"title": "Task from discussion", "description": "Develop sample",
            "project_id": "test", "agent": "deepseek", "mode": "implement", "allowed_paths": ["sample.py"],
            "discussion_id": chat["id"], "context_files": [str(log)]})
        task.update(self.board.task_payload({"title": "Updated title"}, task))
        self.assertEqual(task["discussion_id"], chat["id"])
        self.assertEqual(chat["task_id"], task["id"])
        self.assertEqual(task["context_files"], [str(log.resolve())])
        command = [sys.executable, "-c", "from pathlib import Path; Path('sample.py').write_text('value = 2\\n'); print('AGENTBOARD_STATUS: DONE')"]
        with patch.object(self.board.threading, "Thread"), patch.object(self.board, "command_for", return_value=command):
            run = self.board.start_task(task["id"])["run"]
            self.board.execute_run(run["id"])
        self.assertEqual(run["status"], "review")
        prompt = (self.board.RUNS / run["id"] / "task.txt").read_text(encoding="utf-8")
        self.assertIn("TASK_SPECIFIC_REFERENCE", prompt)
        self.assertIn("APPROVED_SCOPE", prompt)
        self.assertTrue((self.board.RUNS / run["id"] / "context-manifest.json").is_file())

    def test_planning_chat_knows_backlog_without_user_explaining_task(self):
        first = self.task()
        first["description"] = "KEEP_OLD_SAVES_COMPATIBLE"
        following = self.board.create_task({"title": "Follow up", "description": "FOLLOWUP_SCOPE",
            "project_id": "test", "agent": "deepseek", "mode": "explore", "depends_on": [first["id"]]})
        paused = self.board.create_task({"title": "暂停·待定 economy", "description": "Await player choice",
            "project_id": "test", "agent": "deepseek", "mode": "explore"})
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek"})
        command = [sys.executable, "-c", "import sys; sys.stdin.read(); print('Plan discussion only')"]
        with patch.object(self.board.threading, "Thread"), patch.object(self.board, "command_for", return_value=command):
            self.board.send_chat(chat["id"], {"message": "下一步怎么做", "agent": "deepseek"})
            self.board.execute_chat(chat["id"], chat["turn_id"])
        turn = self.board.DATA / "chats" / chat["id"] / chat["turn_id"]
        prompt = (turn / "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("KEEP_OLD_SAVES_COMPATIBLE", prompt)
        self.assertIn("FOLLOWUP_SCOPE", prompt)
        import json
        snapshot = json.loads((turn / "project-briefing.json").read_text(encoding="utf-8"))
        records = {t["id"]: t for t in snapshot["tasks"]}
        self.assertFalse(records[following["id"]]["dependencies_done"])
        self.assertTrue(records[paused["id"]]["explicitly_pending_decision"])
        self.assertEqual(first["status"], "ready")
        self.assertEqual(chat["status"], "idle")

    def test_chat_can_select_task_after_discussing_and_review_old_consensus(self):
        first = self.task()
        second = self.task()
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek"})
        chat["messages"].append({"role": "user", "text": "Which task next?", "created_at": self.board.now()})
        self.board.link_chat_task(chat["id"], {"task_id": first["id"]})
        self.assertEqual(chat["task_id"], first["id"])
        self.assertEqual(len(chat["messages"]), 1)
        self.board.save_chat_consensus(chat["id"], {"consensus": "OLD_TASK_DECISION"})
        first["discussion_id"] = chat["id"]
        self.board.link_chat_task(chat["id"], {"task_id": second["id"]})
        self.assertTrue(chat["consensus_needs_review"])
        self.assertNotIn("OLD_TASK_DECISION", self.board.prompt_for(first))
        self.board.save_chat_consensus(chat["id"], {"consensus": "NEW_TASK_DECISION"})
        self.assertFalse(chat["consensus_needs_review"])

    def group_room(self):
        self.board.STATE["budget"] = {"codex_5h_remaining": 80, "observed_at": self.board.now()}
        return self.board.create_chat({"project_id": "test", "agent": "deepseek", "mode": "group"})

    def fake_group_command(self, calls, handoff=False, fail_codex=False, directives=None, empty_codex=False):
        def command(task, workspace, turn):
            agent = task["agent"]
            calls.append({"agent": agent, "prompt": (turn / "prompt.txt").read_text(encoding="utf-8")})
            if fail_codex and agent == "codex":
                return [sys.executable, "-c", "raise SystemExit(1)"]
            reply = "" if empty_codex and agent == "codex" else agent.upper() + "_SHARED_REPLY"
            directive = directives(agent, len(calls)) if callable(directives) else (directives or {}).get(agent)
            if directive == "INLINE_DONE":
                reply += " AGENTBOARD_TO: DONE"
            elif directive:
                reply += "\nAGENTBOARD_TO: " + directive
            elif handoff:
                reply += "\nAGENTBOARD_TO: " + ("codex" if agent == "deepseek" else "deepseek")
            if agent == "codex":
                code = f"import sys; from pathlib import Path; sys.stdin.read(); Path({str(turn / 'answer.txt')!r}).write_text({reply!r},encoding='utf-8')"
            else:
                code = f"import sys; sys.stdin.read(); print({reply!r})"
            return [sys.executable, "-c", code]
        return command

    def dispatch_group(self, chat, text, calls, discussion_rounds=0, selected="all", **fake_options):
        with patch.object(self.board.threading, "Thread"), patch.object(self.board, "command_for", side_effect=self.fake_group_command(calls, **fake_options)):
            self.board.send_chat(chat["id"], {"message": text, "agent": selected, "discussion_rounds": discussion_rounds})
            self.board.execute_group_chat(chat["id"], chat["batch"]["id"])

    def test_group_broadcast_shares_first_reply_with_second_agent(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "What is next?", calls)
        self.assertEqual([c["agent"] for c in calls], ["deepseek", "codex"])
        self.assertIn("DEEPSEEK_SHARED_REPLY", calls[1]["prompt"])
        self.assertEqual(chat["status"], "idle")
        self.assertEqual(chat["batch"]["completed"], 2)

    def test_group_direct_messages_do_not_wake_others_but_remain_shared(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "/codex Answer only", calls, handoff=True)
        self.assertEqual([c["agent"] for c in calls], ["codex"])
        self.assertIsNone(chat["messages"][-1]["handoff_to"])
        self.dispatch_group(chat, "/deepseek Read the previous reply", calls)
        self.assertEqual([c["agent"] for c in calls], ["codex", "deepseek"])
        self.assertIn("CODEX_SHARED_REPLY", calls[1]["prompt"])
        self.assertEqual(chat["messages"][0]["audience"], ["codex"])

    def test_group_handoffs_cannot_exceed_human_round_limit(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "/讨论 2 Review each other", calls, handoff=True)
        self.assertEqual([c["agent"] for c in calls], ["deepseek", "codex", "deepseek", "codex"])
        self.assertEqual(chat["batch"]["completed"], 4)
        self.assertEqual(chat["status"], "idle")

    def test_group_selected_rounds_continue_without_optional_handoff_markers(self):
        for rounds in [2, 3]:
            with self.subTest(rounds=rounds):
                chat, calls = self.group_room(), []
                self.dispatch_group(chat, "Review together without protocol markers", calls, discussion_rounds=rounds)
                self.assertEqual([call["agent"] for call in calls], ["deepseek", "codex"] * rounds)
                batch = chat["batch"]
                self.assertEqual(batch["completed"], rounds * 2)
                self.assertEqual(batch["requested_rounds"], rounds)
                self.assertEqual(batch["completed_rounds"], rounds)
                self.assertEqual(batch["round"], rounds)
                self.assertEqual(batch["end_reason"], "round_limit")
                self.assertEqual(chat["status"], "idle")
                self.assertIn("CODEX_SHARED_REPLY", calls[2]["prompt"])
                self.assertIn(f"当前为第2/{rounds}轮", calls[2]["prompt"])
                replies = [item for item in chat["messages"] if item["role"] == "assistant"]
                self.assertTrue(all(not item["discussion_done"] for item in replies))
                self.assertEqual([item["discussion_round"] for item in replies], [number for number in range(1, rounds + 1) for _ in range(2)])

    def test_group_explicit_discussion_overrides_body_rounds_without_handoffs(self):
        for command in ["/讨论", "/discuss"]:
            with self.subTest(command=command):
                chat, calls = self.group_room(), []
                self.dispatch_group(chat, command + " 2 Review each other", calls, discussion_rounds=3, selected="codex")
                self.assertEqual([call["agent"] for call in calls], ["deepseek", "codex"] * 2)
                self.assertEqual(chat["batch"]["requested_rounds"], 2)

    def test_group_every_member_done_in_one_round_can_end_early(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "Review together", calls, discussion_rounds=3,
                            directives={"deepseek": "DONE", "codex": "DONE"})
        self.assertEqual([call["agent"] for call in calls], ["deepseek", "codex"])
        self.assertEqual(chat["batch"]["completed_rounds"], 1)
        self.assertEqual(chat["batch"]["requested_rounds"], 3)
        self.assertEqual(chat["batch"]["end_reason"], "agents_done")
        self.assertIn("所有成员", chat["batch"]["finish_detail"])
        self.assertTrue(all(item["discussion_done"] for item in chat["messages"] if item["role"] == "assistant"))

    def test_group_one_done_member_does_not_speak_for_everyone(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "Review together", calls, discussion_rounds=3, directives={"deepseek": "DONE"})
        self.assertEqual(len(calls), 6)
        self.assertEqual(chat["batch"]["end_reason"], "round_limit")
        self.assertEqual(chat["batch"]["completed_rounds"], 3)

    def test_group_done_votes_cannot_accumulate_across_different_rounds(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "Review together", calls, discussion_rounds=3,
                            directives=lambda agent, step: "DONE" if step in (1, 4) else None)
        self.assertEqual(len(calls), 6)
        self.assertEqual(chat["batch"]["end_reason"], "round_limit")

    def test_group_inline_done_is_not_an_explicit_round_termination_vote(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "Review together", calls, discussion_rounds=2,
                            directives={"deepseek": "INLINE_DONE", "codex": "INLINE_DONE"})
        self.assertEqual(len(calls), 4)
        self.assertEqual(chat["batch"]["end_reason"], "round_limit")
        self.assertTrue(all(not item["discussion_done"] for item in chat["messages"] if item["role"] == "assistant"))

    def test_group_selected_or_slash_direct_message_ignores_multiple_rounds(self):
        for message, selected in [("Reply only", "codex"), ("/codex Reply only", "all")]:
            with self.subTest(message=message):
                chat, calls = self.group_room(), []
                self.dispatch_group(chat, message, calls, discussion_rounds=3, selected=selected, handoff=True)
                self.assertEqual([call["agent"] for call in calls], ["codex"])
                self.assertEqual(chat["batch"]["requested_rounds"], 1)
                self.assertEqual(chat["batch"]["end_reason"], "directed_complete")
                self.assertIsNone(chat["messages"][-1]["handoff_to"])

    def test_group_explicit_all_remains_one_broadcast_despite_selected_rounds(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "/all Broadcast this", calls, discussion_rounds=3, handoff=True)
        self.assertEqual([call["agent"] for call in calls], ["deepseek", "codex"])
        self.assertEqual(chat["batch"]["rounds"], 0)
        self.assertEqual(chat["batch"]["completed_rounds"], 1)
        self.assertEqual(chat["batch"]["end_reason"], "broadcast_complete")

    def test_group_three_members_cannot_exceed_six_replies(self):
        self.board.save_agent({"id": "sim-three", "name": "Third simulator", "kind": "mock"})
        self.board.STATE["budget"] = {"codex_5h_remaining": 80, "observed_at": self.board.now()}
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek", "mode": "group",
                                       "members": ["deepseek", "codex", "sim-three"]})
        calls = []
        self.dispatch_group(chat, "Review together", calls, discussion_rounds=3, handoff=True)
        self.assertEqual([call["agent"] for call in calls], ["deepseek", "codex", "sim-three"] * 2)
        self.assertEqual(chat["batch"]["completed"], 6)
        self.assertEqual(chat["batch"]["completed_rounds"], 2)
        self.assertEqual(chat["batch"]["round"], 2)
        self.assertEqual(chat["batch"]["requested_rounds"], 3)
        self.assertEqual(chat["batch"]["end_reason"], "reply_limit")

    def test_group_quota_skip_does_not_repeat_a_single_available_member(self):
        chat, calls = self.group_room(), []
        self.board.STATE["budget"]["codex_5h_remaining"] = 15
        self.dispatch_group(chat, "Review together", calls, discussion_rounds=3)
        self.assertEqual([call["agent"] for call in calls], ["deepseek"])
        self.assertEqual(chat["batch"]["completed"], 1)
        self.assertEqual(chat["batch"]["completed_rounds"], 0)
        self.assertEqual(chat["batch"]["skipped_agents"], ["codex"])
        self.assertEqual(chat["batch"]["end_reason"], "quota_limited")
        self.assertEqual(chat["status"], "idle")

    def test_group_quota_is_rechecked_each_codex_turn_and_preserves_prior_round(self):
        chat, calls = self.group_room(), []
        with patch.object(self.board, "guard_codex_chat_budget", side_effect=[None, ValueError("quota fixture")]) as guard:
            self.dispatch_group(chat, "Review together", calls, discussion_rounds=3)
        self.assertEqual(guard.call_count, 2)
        self.assertEqual([call["agent"] for call in calls], ["deepseek", "codex", "deepseek"])
        self.assertEqual(chat["batch"]["completed"], 3)
        self.assertEqual(chat["batch"]["completed_rounds"], 1)
        self.assertEqual(chat["batch"]["end_reason"], "quota_limited")

    def test_group_four_member_partial_round_does_not_claim_round_completion(self):
        for name in ["sim-three", "sim-four"]:
            self.board.save_agent({"id": name, "name": name, "kind": "mock"})
        self.board.STATE["budget"] = {"codex_5h_remaining": 80, "observed_at": self.board.now()}
        members = ["deepseek", "codex", "sim-three", "sim-four"]
        chat = self.board.create_chat({"project_id": "test", "agent": "deepseek", "mode": "group", "members": members})
        calls = []
        self.dispatch_group(chat, "Review together", calls, discussion_rounds=3)
        self.assertEqual([call["agent"] for call in calls], members + members[:2])
        self.assertEqual(chat["batch"]["completed"], 6)
        self.assertEqual(chat["batch"]["completed_rounds"], 1)
        self.assertEqual(chat["batch"]["round"], 2)
        self.assertEqual(chat["batch"]["end_reason"], "reply_limit")

    def test_group_deadline_during_discussion_preserves_successful_reply(self):
        chat = self.group_room()
        clock = {"value": 0.0}
        def reply(chat_id, turn_id, batch, deadline):
            chat["messages"].append({"role": "assistant", "agent": "deepseek", "text": "completed fixture reply"})
            clock["value"] = 1501.0
            return True
        with patch.object(self.board.threading, "Thread"), patch.object(self.board.time, "monotonic", side_effect=lambda: clock["value"]), patch.object(self.board, "execute_chat", side_effect=reply) as worker:
            self.board.send_chat(chat["id"], {"message": "Review", "agent": "all", "discussion_rounds": 3})
            self.board.execute_group_chat(chat["id"], chat["batch"]["id"])
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(chat["batch"]["completed"], 1)
        self.assertEqual(chat["batch"]["completed_rounds"], 0)
        self.assertEqual(chat["batch"]["end_reason"], "deadline")
        self.assertEqual(chat["messages"][-1]["text"], "completed fixture reply")

    def test_group_one_member_discussion_is_one_broadcast_not_self_repetition(self):
        self.board.STATE["budget"] = {"codex_5h_remaining": 80, "observed_at": self.board.now()}
        for message in ["Review together", "/讨论 3 Review"]:
            with self.subTest(message=message):
                chat = self.board.create_chat({"project_id": "test", "agent": "codex", "mode": "group", "members": ["codex"]})
                calls = []
                self.dispatch_group(chat, message, calls, discussion_rounds=3, handoff=True)
                self.assertEqual([call["agent"] for call in calls], ["codex"])
                self.assertEqual(chat["batch"]["rounds"], 0)
                self.assertEqual(chat["batch"]["requested_rounds"], 1)
                self.assertEqual(chat["batch"]["completed_rounds"], 1)
                self.assertEqual(chat["batch"]["max_replies"], 1)
                self.assertEqual(chat["batch"]["end_reason"], "broadcast_complete")
                self.assertEqual(chat["status"], "idle")

    def test_group_empty_reply_stops_later_rounds_and_keeps_existing_reply(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "Review together", calls, discussion_rounds=3, empty_codex=True)
        self.assertEqual([call["agent"] for call in calls], ["deepseek", "codex"])
        self.assertEqual(chat["batch"]["completed"], 1)
        self.assertEqual(chat["batch"]["completed_rounds"], 0)
        self.assertEqual(chat["batch"]["end_reason"], "reply_failed")
        self.assertIn("没有返回回复", chat["error"])
        self.assertTrue(any(item.get("agent") == "deepseek" for item in chat["messages"]))

    def test_group_budget_skips_codex_without_stopping_deepseek(self):
        chat, calls = self.group_room(), []
        self.board.STATE["budget"]["codex_5h_remaining"] = 15
        self.dispatch_group(chat, "Everyone answer", calls)
        self.assertEqual([c["agent"] for c in calls], ["deepseek"])
        self.assertTrue(any(m["role"] == "system" and "Codex" in m["text"] for m in chat["messages"]))
        self.assertEqual(chat["status"], "idle")
        before = len(chat["messages"])
        with self.assertRaises(ValueError):
            self.board.send_chat(chat["id"], {"message": "/codex Hello", "agent": "all"})
        self.assertEqual(len(chat["messages"]), before)

    def test_group_stop_cancels_pending_replies(self):
        chat = self.group_room()
        def reply(chat_id, turn_id, batch, deadline):
            chat["messages"].append({"role": "assistant", "agent": "deepseek", "text": "first reply"})
            self.board.stop_chat(chat_id)
            return True
        with patch.object(self.board.threading, "Thread"), patch.object(self.board, "execute_chat", side_effect=reply) as worker:
            self.board.send_chat(chat["id"], {"message": "Review", "agent": "all"})
            self.board.execute_group_chat(chat["id"], chat["batch"]["id"])
            self.assertEqual(worker.call_count, 1)
        self.assertEqual(chat["batch"]["status"], "stopped")
        self.assertEqual(chat["batch"]["end_reason"], "stopped")
        self.assertEqual(chat["batch"]["completed_rounds"], 0)

    def test_group_failure_preserves_completed_reply(self):
        chat, calls = self.group_room(), []
        self.dispatch_group(chat, "Review", calls, fail_codex=True)
        self.assertEqual(chat["status"], "error")
        self.assertTrue(any(m.get("agent") == "deepseek" and "SHARED_REPLY" in m["text"] for m in chat["messages"]))

    def test_group_deadline_prevents_further_model_calls(self):
        chat = self.group_room()
        with patch.object(self.board.threading, "Thread"):
            self.board.send_chat(chat["id"], {"message": "Review", "agent": "all"})
        with patch.object(self.board.time, "monotonic", side_effect=[0.0, 1501.0]), patch.object(self.board, "execute_chat") as worker:
            self.board.execute_group_chat(chat["id"], chat["batch"]["id"])
            worker.assert_not_called()
        self.assertIn("25分钟", chat["error"])
        self.assertEqual(chat["batch"]["end_reason"], "deadline")


if __name__ == "__main__":
    unittest.main()
