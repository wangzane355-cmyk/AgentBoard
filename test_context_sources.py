import io
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from context_sources import materialize_context, validate_references


class ReferenceTests(unittest.TestCase):
    def test_directory_scan_keeps_logs_and_reports_tail_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "开发日志.md").write_text("LATEST_HEAD\n" + "old entry\n" * 2000 + "LATEST_DECISION", encoding="utf-8")
            (docs / "credentials.json").write_text("DO_NOT_ATTACH", encoding="utf-8")
            result = materialize_context({"context_files": [str(docs)]}, None, root / "snapshot")
            self.assertEqual(len(result["sources"]), 1)
            self.assertIn("LATEST_DECISION", result["prompt"])
            self.assertIn("LATEST_HEAD", result["prompt"])
            self.assertNotIn("DO_NOT_ATTACH", result["prompt"])
            self.assertTrue(result["sources"][0]["truncated"])

    def test_same_filename_has_unique_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name in ("one", "two"):
                folder = root / name
                folder.mkdir()
                path = folder / "README.md"
                path.write_text(name, encoding="utf-8")
                paths.append(str(path))
            result = materialize_context({"context_files": paths}, None, root / "snapshot")
            self.assertEqual(len({s["snapshot"] for s in result["sources"]}), 2)

    def test_url_fetch_extracts_text_without_scripts(self):
        response = io.BytesIO(b"<html><h1>Latest plan</h1><script>hidden()</script><p>Keep compatibility</p></html>")
        response.headers = Message()
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.geturl = lambda: "https://example.test/plan"
        with tempfile.TemporaryDirectory() as directory, patch("context_sources.urlopen", return_value=response):
            result = materialize_context({"context_urls": ["https://example.test/plan"]}, None, Path(directory))
        self.assertIn("Keep compatibility", result["prompt"])
        self.assertNotIn("hidden()", result["prompt"])

    def test_invalid_url_and_missing_path_are_rejected(self):
        for body in ({"context_urls": ["file:///private"]}, {"context_files": ["relative/path"]}):
            with self.assertRaises(ValueError):
                validate_references(body)


if __name__ == "__main__":
    unittest.main()
