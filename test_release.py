import tempfile
import unittest
import zipfile
from pathlib import Path

from package_release import package


class ReleaseTests(unittest.TestCase):
    def test_runtime_credentials_and_worker_state_are_never_packaged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "server.py").write_text("# public\n")
            (root / "README.md").write_text("public")
            for name in ("data", ".git", ".codex", "docs/data", "static/node_modules"):
                folder = root / name
                folder.mkdir(parents=True)
                (folder / "credentials.json").write_text("private-fixture")
            (root / "auth.json").write_text("private-fixture")
            (root / ".env").write_text("private-fixture")
            (root / "private_helper.py").write_text("private-fixture")
            (root / "docs/private.key").write_text("private-fixture")
            output = root / "data/release.zip"
            package(root, output)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertIn("AgentBoard/server.py", names)
                self.assertIn("AgentBoard/SOURCE_MANIFEST.json", names)
                self.assertFalse(any("credentials" in name or "/data/" in name or "auth.json" in name or ".env" in name for name in names))
                self.assertNotIn(b"private-fixture", b"".join(archive.read(name) for name in names))
            self.assertTrue(output.with_suffix(".zip.sha256").is_file())


if __name__ == "__main__":
    unittest.main()
