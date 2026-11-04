"""Acceptance integrity tests, entirely offline."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from verification import RenderedText, command_argv, run_verification, validate_checks, verification_files


class VerificationTests(unittest.TestCase):
    def test_commands_reject_external_paths(self):
        for path in ("../private", "/outside", "C:\\private", "--rootdir=../private", "tests/../../outside"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                command_argv(["python", "-m", "unittest", "discover", "-s", path])
        self.assertIn("tests", command_argv(["python", "-m", "unittest", "discover", "-s", "tests"]))

    def test_compile_commands_cannot_be_only_acceptance(self):
        with self.assertRaises(ValueError):
            validate_checks([{"kind": "command", "argv": ["python", "-m", "compileall", "."]}])

    def test_rendered_text_ignores_source_and_hidden_content(self):
        parser = RenderedText()
        parser.feed('<head><title>Secret A</title></head><script>Secret B</script><style>Secret C</style>'
                    '<div hidden>Secret D <span>nested</span></div><div aria-hidden="true">Secret E</div>'
                    '<div style="display:none">Secret F</div><template>Secret G</template><h1>Visible</h1>')
        self.assertEqual("".join(parser.text), "Visible")

    def test_node_discovery_locks_existing_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "tests").mkdir()
            (root / "tests/check.cjs").write_text("// fixture")
            (root / "app.js").write_text("// implementation")
            result = verification_files(root, [{"kind": "node_test", "paths": []}])
            self.assertEqual(set(result), {"tests/check.cjs"})

    def test_class_specific_unittest_locks_module(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "test_app.py").write_text("# fixture")
            result = verification_files(root, [{"kind": "python_unittest", "modules": ["test_app.Case.method"]}])
            self.assertEqual(set(result), {"test_app.py"})

    def test_timeout_becomes_failed_check_for_repair(self):
        class Runner:
            def checkpoint(self):
                pass
            def run(self, *args, **kwargs):
                raise TimeoutError("fixture timeout")
        with tempfile.TemporaryDirectory() as folder:
            checks = validate_checks([{"kind": "python_unittest"}])
            result = run_verification(checks, folder, Path(folder) / "evidence", Runner())
            self.assertFalse(result[0]["passed"])
            self.assertIn("fixture timeout", result[0]["detail"])

    def test_web_requires_measured_viewport_and_no_overflow(self):
        import json
        class Runner:
            def checkpoint(self):
                pass
            def run(inner, argv, cwd, destination, timeout):
                destination.mkdir(parents=True, exist_ok=True)
                image = Path(argv[-2])
                image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
                Path(str(image) + ".json").write_text(json.dumps(measurement))
                stderr = destination / "stderr.txt"
                stderr.write_text("")
                return {"exit_code": 0, "stderr": str(stderr)}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "index.html").write_text("<h1>Visible</h1>")
            checks = validate_checks([{"kind": "web", "expected_text": ["Visible"], "viewports": [[390, 844]]}])
            with patch("verification.browser_executable", return_value="fixture-browser"), patch("verification.shutil.which", return_value="fixture-node"):
                for measured_width, scroll_width, expected in ((500, 500, False), (390, 600, False), (390, 390, True)):
                    measurement = {"width": measured_width, "height": 844, "scrollWidth": scroll_width, "text": "Visible"}
                    with self.subTest(width=measured_width, overflow=scroll_width):
                        result = run_verification(checks, folder, Path(folder) / "checks", Runner())
                        self.assertEqual(result[0]["passed"], expected)


if __name__ == "__main__":
    unittest.main()
