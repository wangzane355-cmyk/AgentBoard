"""Offline launcher lifecycle checks. Never starts the board, browsers or models."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import launch


class Clock:
    def __init__(self):
        self.elapsed = 0.0

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds


def response(body, status=200):
    value = MagicMock()
    value.status = status
    value.read.return_value = body
    value.__enter__.return_value = value
    return value


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name)

    def test_windowless_streams_are_recorded_in_private_log(self):
        with patch.dict(launch.os.environ, {"AGENTBOARD_DATA_DIR": str(self.data)}), patch.object(launch.sys, "stdout", None), patch.object(launch.sys, "stderr", None):
            launch.prepare_windowless_logging()
            output, error = launch.sys.stdout, launch.sys.stderr
            output.write("windowless startup fixture：启动中\n")
            error.write("windowless diagnostics fixture：中文错误\n")
            output.flush()
        output.close()
        self.assertIs(output, error)
        self.assertIn("windowless diagnostics fixture：中文错误", (self.data / "launcher.log").read_text(encoding="utf-8"))

    def test_ready_requires_health_identity_and_actual_page(self):
        health = response(json.dumps({"app": "AgentBoard", "ready": True}).encode())
        page = response(b"<!doctype html><title>AgentBoard</title>")
        with patch.object(launch, "urlopen", side_effect=[health, page]) as opened:
            self.assertTrue(launch.page_ready(9876))
        self.assertEqual([call.args[0] for call in opened.call_args_list],
                         ["http://127.0.0.1:9876/api/health", "http://127.0.0.1:9876/"])

    def test_ready_rejects_unrelated_unready_or_malformed_health(self):
        for body in (b'{"app":"Other","ready":true}', b'{"app":"AgentBoard","ready":false}', b"[]", b"not-json"):
            with self.subTest(body=body), patch.object(launch, "urlopen", return_value=response(body)) as opened:
                self.assertFalse(launch.page_ready())
                self.assertEqual(opened.call_count, 1)
        with patch.object(launch, "urlopen", side_effect=ConnectionResetError):
            self.assertFalse(launch.page_ready())

    def test_valid_health_with_unrelated_page_is_not_ready(self):
        health = response(b'{"app":"AgentBoard","ready":true}')
        with patch.object(launch, "urlopen", side_effect=[health, response(b"unrelated service")]):
            self.assertFalse(launch.page_ready())

    def test_ready_board_is_reused_without_startup_lock_or_spawn(self):
        with patch.object(launch, "page_ready", return_value=True), patch.object(launch, "StartupLock") as lock, patch.object(launch, "start_background") as start:
            launch.ensure_running(data=self.data)
        lock.assert_not_called()
        start.assert_not_called()

    def test_slow_start_beyond_old_wait_limit_eventually_opens(self):
        clock = Clock()
        child = MagicMock()
        child.poll.return_value = None
        progress = []
        with patch.object(launch, "time", clock), patch.object(launch, "page_ready", side_effect=lambda port: clock.elapsed >= 45), patch.object(launch, "already_running", return_value=False), patch.object(launch, "start_background", return_value=child) as start:
            launch.ensure_running(data=self.data, timeout=120, progress=lambda message, elapsed: progress.append(elapsed))
        self.assertEqual(clock.elapsed, 45)
        self.assertGreater(max(progress), 25)
        start.assert_called_once_with(8765, self.data)
        child.terminate.assert_not_called()

    def test_background_exit_is_reported_without_opening_bad_page(self):
        child = MagicMock()
        child.poll.return_value = 7
        with patch.object(launch, "page_ready", return_value=False), patch.object(launch, "already_running", return_value=False), patch.object(launch, "start_background", return_value=child), patch.object(launch.webbrowser, "open") as browser:
            with self.assertRaisesRegex(launch.StartupError, "后台没有成功启动"):
                launch.ensure_running(data=self.data)
        browser.assert_not_called()
        child.terminate.assert_not_called()
        child.kill.assert_not_called()

    def test_losing_child_can_reuse_another_ready_entry_point(self):
        child = MagicMock()
        child.poll.return_value = 1
        with patch.object(launch, "page_ready", side_effect=[False, False, False, True]), patch.object(launch, "already_running", return_value=False), patch.object(launch, "start_background", return_value=child):
            launch.ensure_running(data=self.data)
        child.terminate.assert_not_called()

    def test_unrelated_occupied_port_does_not_spawn_or_terminate(self):
        clock = Clock()
        with patch.object(launch, "time", clock), patch.object(launch, "page_ready", return_value=False), patch.object(launch, "already_running", return_value=True), patch.object(launch, "start_background") as start:
            with self.assertRaisesRegex(launch.StartupError, "端口可能被其他程序占用"):
                launch.ensure_running(data=self.data, timeout=1)
        start.assert_not_called()

    def test_waiting_for_other_launcher_times_out_without_spawn(self):
        clock = Clock()
        with launch.StartupLock(self.data / "launcher-8765.lock") as owner:
            self.assertTrue(owner.acquire())
            with patch.object(launch, "time", clock), patch.object(launch, "page_ready", return_value=False), patch.object(launch, "start_background") as start:
                with self.assertRaisesRegex(launch.StartupError, "另一次启动还没有完成"):
                    launch.ensure_running(data=self.data, timeout=1)
            start.assert_not_called()

    def test_cancel_after_spawn_does_not_stop_background(self):
        child = MagicMock()
        child.poll.return_value = None
        calls = 0
        def progress(message, elapsed):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise launch.LaunchCancelled()
        with patch.object(launch, "page_ready", return_value=False), patch.object(launch, "already_running", return_value=False), patch.object(launch, "start_background", return_value=child):
            with self.assertRaises(launch.LaunchCancelled):
                launch.ensure_running(data=self.data, progress=progress)
        child.terminate.assert_not_called()
        child.kill.assert_not_called()
        with launch.StartupLock(self.data / "launcher-8765.lock") as unlocked:
            self.assertTrue(unlocked.acquire())

    def test_background_uses_absolute_current_python_fixed_cwd_and_private_log(self):
        with patch.object(launch.subprocess, "Popen") as popen:
            launch.start_background(9876, self.data)
        argv = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(argv[0], sys.executable)
        self.assertTrue(Path(argv[0]).is_absolute())
        self.assertEqual(argv[4], str(launch.BASE / "server.py"))
        self.assertEqual(argv[-3:], ["--no-browser", "--port", "9876"])
        self.assertEqual(options["cwd"], launch.BASE)
        self.assertEqual(options["env"]["AGENTBOARD_DATA_DIR"], str(self.data))
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertIs(options["stdout"], options["stderr"])
        self.assertEqual(Path(options["stdout"].name), self.data / "launcher.log")

    def test_windowless_entry_keeps_background_program_stable_for_phone_firewall(self):
        windowed = self.data / "pythonw.exe"
        console = self.data / "python.exe"
        for sibling_exists in (False, True):
            with self.subTest(sibling_exists=sibling_exists):
                if sibling_exists:
                    console.write_bytes(b"fixture - never executed")
                with patch.object(launch.sys, "executable", str(windowed)), patch.object(launch.subprocess, "Popen") as popen:
                    launch.start_background(9876, self.data)
                self.assertEqual(popen.call_args.args[0][0], str(console if sibling_exists else windowed))
                self.assertEqual(popen.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def test_main_reports_startup_error_visibly_and_closes_progress(self):
        with patch.object(launch, "StartupProgress") as progress, patch.object(launch, "prepare_windowless_logging"), patch.object(launch, "ensure_running", side_effect=launch.StartupError("fixture failure")), patch.object(launch, "show_error") as error, patch.object(launch.webbrowser, "open") as browser:
            self.assertEqual(launch.main(), 1)
        error.assert_called_once_with("fixture failure")
        browser.assert_not_called()
        self.assertTrue(progress.return_value.close.called)

    def test_main_reports_browser_failure_after_successful_start(self):
        with patch.object(launch, "StartupProgress"), patch.object(launch, "prepare_windowless_logging"), patch.object(launch, "ensure_running") as ensure, patch.object(launch, "show_error") as error, patch.object(launch.webbrowser, "open", return_value=False):
            self.assertEqual(launch.main(), 1)
        ensure.assert_called_once()
        self.assertIn("后台已经就绪", error.call_args.args[0])

    def test_main_cancel_is_normal_and_does_not_open_or_report_error(self):
        with patch.object(launch, "StartupProgress"), patch.object(launch, "prepare_windowless_logging"), patch.object(launch, "ensure_running", side_effect=launch.LaunchCancelled()), patch.object(launch, "show_error") as error, patch.object(launch.webbrowser, "open") as browser, patch.object(launch.sys, "stdout", io.StringIO()):
            self.assertEqual(launch.main(), 0)
        error.assert_not_called()
        browser.assert_not_called()

    def test_main_legacy_console_encoding_never_blocks_lifecycle_or_native_errors(self):
        cases = [
            ("success", None, True, 0, True, None),
            ("cancelled", launch.LaunchCancelled(), True, 0, False, None),
            ("startup_error", launch.StartupError("中文启动失败"), True, 1, False, "中文启动失败"),
            ("browser_error", None, False, 1, True, "后台已经就绪"),
            ("unexpected_error", RuntimeError("中文意外异常"), True, 1, False, "中文意外异常"),
        ]
        for name, failure, browser_ready, expected, opens_browser, error_text in cases:
            with self.subTest(case=name):
                output_bytes, error_bytes = io.BytesIO(), io.BytesIO()
                output = io.TextIOWrapper(output_bytes, encoding="cp1252", errors="strict")
                error = io.TextIOWrapper(error_bytes, encoding="cp1252", errors="strict")
                try:
                    # Force a strict English-Windows code page even when the test
                    # runner is UTF-8. Mock only the native window, not show_error.
                    with patch.object(launch.sys, "stdout", output), patch.object(launch.sys, "stderr", error), patch.object(launch, "StartupProgress") as progress, patch.object(launch, "ensure_running", side_effect=failure) as ensure, patch.object(launch.webbrowser, "open", return_value=browser_ready) as browser, patch.object(launch, "data_directory", return_value=self.data), patch.object(launch.os, "name", "nt"), patch("ctypes.windll", create=True) as windows:
                        self.assertEqual(launch.main(), expected)
                    ensure.assert_called_once()
                    self.assertEqual(browser.called, opens_browser)
                    self.assertTrue(progress.return_value.close.called)
                    output.flush()
                    error.flush()
                    console = output_bytes.getvalue().decode("cp1252")
                    diagnostics = error_bytes.getvalue().decode("cp1252")
                    self.assertIn("AgentBoard", console)
                    self.assertNotIn("UnicodeEncodeError", diagnostics)
                    if error_text:
                        windows.user32.MessageBoxW.assert_called_once()
                        self.assertIn(error_text, windows.user32.MessageBoxW.call_args.args[1])
                        self.assertIn("http://127.0.0.1:8765/", diagnostics)
                    else:
                        windows.user32.MessageBoxW.assert_not_called()
                    if name == "unexpected_error":
                        self.assertIn("Traceback", diagnostics)
                        self.assertIn("RuntimeError", diagnostics)
                finally:
                    output.close()
                    error.close()

    def test_main_preserves_unicode_on_stringio_without_reconfigure(self):
        output, error = io.StringIO(), io.StringIO()
        with patch.object(launch.sys, "stdout", output), patch.object(launch.sys, "stderr", error), patch.object(launch, "StartupProgress"), patch.object(launch, "ensure_running") as ensure, patch.object(launch.webbrowser, "open", return_value=True):
            self.assertEqual(launch.main(), 0)
        ensure.assert_called_once()
        self.assertIn("正在打开 AgentBoard", output.getvalue())
        self.assertIn("AgentBoard 已就绪，已打开页面。", output.getvalue())
        self.assertEqual(error.getvalue(), "")

    def test_progress_cancel_closes_only_its_own_window(self):
        progress = launch.StartupProgress()
        window = progress.root = MagicMock()
        progress.cancel()
        self.assertTrue(progress.cancelled)
        window.destroy.assert_called_once()
        with self.assertRaises(launch.LaunchCancelled):
            progress.update("fixture", 1)

    def test_parallel_process_launchers_share_real_os_lock_and_start_once(self):
        script = '''
import sys,time,threading
from pathlib import Path
import launch
root=Path(sys.argv[1])
deadline=time.monotonic()+8
while not (root/"go").exists():
    if time.monotonic()>deadline: raise RuntimeError("fixture barrier timeout")
    time.sleep(.02)
launch.page_ready=lambda port:(root/"ready").exists()
launch.already_running=lambda port:False
class Child:
    def poll(self): return None
def start(port,data):
    with (root/"starts").open("a") as output: output.write("one\\n")
    def ready():
        time.sleep(.7)
        (root/"ready").write_text("ready")
    threading.Thread(target=ready).start()
    return Child()
launch.start_background=start
launch.ensure_running(port=9876,data=root,timeout=8)
'''
        children = [subprocess.Popen([sys.executable, "-B", "-c", script, str(self.data)], cwd=launch.BASE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        (self.data / "go").write_text("go")
        for child in children:
            stdout, stderr = child.communicate(timeout=12)
            self.assertEqual(child.returncode, 0, stdout + stderr)
        self.assertEqual((self.data / "starts").read_text().splitlines(), ["one"])

    def test_os_lock_is_released_when_owner_process_exits_abruptly(self):
        path = self.data / "crash.lock"
        script = 'import os,sys; import launch; lock=launch.StartupLock(sys.argv[1]); lock.__enter__(); assert lock.acquire(); os._exit(0)'
        result = subprocess.run([sys.executable, "-B", "-c", script, str(path)], cwd=launch.BASE,
                                capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        with launch.StartupLock(path) as next_owner:
            self.assertTrue(next_owner.acquire())


if __name__ == "__main__":
    unittest.main()
