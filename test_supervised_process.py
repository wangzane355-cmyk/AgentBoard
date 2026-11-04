"""Own-child lifecycle tests. No model, credentials, browser or network required."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from supervised_process import ProcessRunner, WorkInterrupted, same_process
from verification import run_verification, validate_checks


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.records = []
        self.runner = ProcessRunner(lambda: None, lambda records: self.records.extend(records), stall_seconds=0)
        self.addCleanup(self.runner.close)

    def test_completed_json_stream_reports_real_usage_and_session(self):
        script = 'import json; print(json.dumps({"type":"thread.started","thread_id":"fixture"})); print(json.dumps({"type":"turn.completed","usage":{"input_tokens":7,"output_tokens":3}}))'
        result = self.runner.run([sys.executable, "-c", script], self.root, self.root / "logs", 5, json_events=True)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["usage"]["output_tokens"], 3)
        self.assertEqual(result["session_id"], "fixture")
        self.assertEqual(self.runner.active, {})

    def test_timeout_terminates_only_the_owned_child(self):
        with self.assertRaises(TimeoutError):
            self.runner.run([sys.executable, "-c", "import time; time.sleep(10)"], self.root, self.root / "timeout", 0.3)
        self.assertTrue(self.records)
        self.assertTrue(all(not same_process(record) for record in self.records))
        self.assertEqual(self.runner.active, {})

    def test_pause_interrupts_running_process(self):
        started = time.monotonic()
        self.runner.control = lambda: "pause" if time.monotonic() - started > 0.2 else None
        with self.assertRaises(WorkInterrupted):
            self.runner.run([sys.executable, "-c", "import time; time.sleep(10)"], self.root, self.root / "paused", 5)
        self.assertTrue(all(not same_process(record) for record in self.records))

    def test_unrelated_api_secret_is_not_inherited_by_checks(self):
        with patch.dict(os.environ, {"UNRELATED_API_KEY": "fixture-secret"}):
            result = self.runner.run([sys.executable, "-c", 'import os; print("present" if "UNRELATED_API_KEY" in os.environ else "absent")'],
                                     self.root, self.root / "environment", 5)
        self.assertEqual(Path(result["stdout"]).read_text().strip(), "absent")

    def test_zero_discovered_tests_cannot_pass(self):
        (self.root / "test_empty.py").write_text("# no test cases\n", encoding="utf-8")
        checks = validate_checks([{"kind": "python_unittest", "modules": ["test_empty"]}])
        result = run_verification(checks, self.root, self.root / "checks", self.runner)
        self.assertFalse(result[0]["passed"])
        self.assertEqual(result[0]["tests"], 0)

    def test_missing_browser_is_explicitly_unrun(self):
        (self.root / "index.html").write_text("<h1>Fixture</h1>", encoding="utf-8")
        checks = validate_checks([{"kind": "web", "expected_text": ["Fixture"]}])
        with patch("verification.browser_executable", return_value=None):
            result = run_verification(checks, self.root, self.root / "browser-check", self.runner)
        self.assertFalse(result[0]["passed"])
        self.assertEqual(result[0]["artifacts"], [])


if __name__ == "__main__":
    unittest.main()
