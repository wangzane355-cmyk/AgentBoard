"""Offline selection, precedence, argument and evidence tests; no model calls."""
import json
import tempfile
import unittest
from pathlib import Path

from model_settings import ModelSettings, codex_arguments, execution_record, local_defaults


class ModelSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        self.config = self.home / "config.toml"
        self.config.write_text('model = "fixture-one"\nmodel_reasoning_effort = "low"\n[profiles.other]\nmodel = "wrong"\n', encoding="utf-8")
        (self.home / "models_cache.json").write_text(json.dumps({"identity": "do-not-expose", "models": [
            {"slug": "fixture-one", "visibility": "list", "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}]},
            {"slug": "fixture-two", "visibility": "list", "supported_reasoning_levels": [{"effort": "medium"}]},
            {"slug": "hidden", "visibility": "hide", "supported_reasoning_levels": []}]}), encoding="utf-8")
        self.settings = ModelSettings(self.root / "data", self.home)

    def test_defaults_are_untouched_and_catalog_is_sanitized(self):
        before = self.config.read_bytes()
        self.assertEqual(local_defaults(self.home)["model"], "fixture-one")
        self.assertEqual(self.settings.resolve("codex"), {"model": "", "reasoning_effort": ""})
        public = self.settings.status()
        self.assertNotIn("do-not-expose", json.dumps(public))
        self.assertNotIn("hidden", json.dumps(public))
        self.settings.save({"model": "fixture-one", "reasoning_effort": "high"})
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(ModelSettings(self.root / "data", self.home).resolve("codex")["reasoning_effort"], "high")

    def test_validation_precedence_and_fallback(self):
        self.settings.save({"model": "fixture-one", "reasoning_effort": "low"})
        self.assertEqual(self.settings.resolve("codex", {"reasoning_effort": "high"})["reasoning_effort"], "high")
        self.assertEqual(self.settings.resolve("deepseek", {"model": "fixture-one"}), {})
        for options in ({"model": "unknown"}, {"model": "fixture-two", "reasoning_effort": "high"},
                        {"reasoning_effort": "invented"}, {"args": "--unsafe"}, {"model": []}, ["invalid"]):
            with self.assertRaises(ValueError):
                self.settings.resolve("codex", options)
        self.settings.save({})
        self.assertEqual(self.settings.resolve("codex", {"reasoning_effort": "high"})["model"], "fixture-one")

    def test_argument_boundaries_and_recovery(self):
        options = {"model": "fixture-one", "reasoning_effort": "high"}
        self.assertEqual(codex_arguments(options), ["--model", "fixture-one", "-c", 'model_reasoning_effort="high"'])
        self.settings.save(options)
        self.settings.save({})
        self.assertEqual(codex_arguments(self.settings.resolve("codex")), [])
        (self.home / "models_cache.json").write_text("broken", encoding="utf-8")
        self.assertEqual(self.settings.status()["codex"]["models"][0]["efforts"], [])
        with self.assertRaises(ValueError):
            self.settings.save({"reasoning_effort": "high"})

    def test_evidence_requires_runtime_header(self):
        path = self.root / "stderr.txt"
        requested = {"model": "fixture-one", "reasoning_effort": "high"}
        record = execution_record("codex", requested, path)
        self.assertEqual(record["confirmed"], {})
        path.write_text('OpenAI Codex\n--------\nmodel: fixture-one\nreasoning effort: high\n--------\nuser\nmodel: fake\n', encoding="utf-8")
        record = execution_record("codex", requested, path)
        self.assertEqual(record["confirmed"], requested)
        self.assertEqual(record["source"], "executor_log")
        path.write_text('user\nmodel: fake\n', encoding="utf-8")
        self.assertEqual(execution_record("codex", {}, path)["confirmed"], {})


if __name__ == "__main__":
    unittest.main()
