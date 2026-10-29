"""Launcher checks do not open browsers or invoke models."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import launch


class LauncherTests(unittest.TestCase):
    def test_windowless_streams_are_recorded_in_private_log(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(launch.os.environ, {"AGENTBOARD_DATA_DIR": directory}), patch.object(launch.sys, "stdout", None), patch.object(launch.sys, "stderr", None):
                launch.prepare_windowless_logging()
                output = launch.sys.stdout
                error = launch.sys.stderr
                output.write("windowless startup fixture\n")
                error.write("windowless diagnostics fixture\n")
                output.flush()
            output.close()
            self.assertIs(output, error)
            self.assertIn("windowless diagnostics fixture", (Path(directory)/"launcher.log").read_text(encoding="utf-8"))

    def test_ready_requires_actual_agentboard_page(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b"<!doctype html><title>AgentBoard</title>"
        opener = MagicMock()
        opener.__enter__.return_value = response
        with patch.object(launch, "urlopen", return_value=opener):
            self.assertTrue(launch.page_ready())
            response.read.return_value = b"unrelated service"
            self.assertFalse(launch.page_ready())
        with patch.object(launch, "urlopen", side_effect=ConnectionResetError):
            self.assertFalse(launch.page_ready())


if __name__ == "__main__":
    unittest.main()
