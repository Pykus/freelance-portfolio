"""Regression and integration tests for the portable backup manifest."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backup_manifest import build, check, validate, inventory

class ManifestTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.folder = self.root / "data"
        self.folder.mkdir()
        self.file = self.folder / "notes.txt"
        self.file.write_text("synthetic contents", encoding="utf-8")
        self.manifest = self.root / "manifest.json"

    def test_roundtrip(self):
        build(self.folder, self.manifest)
        self.assertTrue(check(self.folder, self.manifest)["ok"])

    def test_modified_content(self):
        build(self.folder, self.manifest)
        self.file.write_text("edited contents", encoding="utf-8")
        self.assertEqual(check(self.folder, self.manifest)["changed"], ["notes.txt"])

    def test_missing_file(self):
        build(self.folder, self.manifest)
        self.file.unlink()
        self.assertEqual(check(self.folder, self.manifest)["missing"], ["notes.txt"])

    def test_new_file(self):
        build(self.folder, self.manifest)
        (self.folder / "new.txt").write_text("new", encoding="utf-8")
        self.assertEqual(check(self.folder, self.manifest)["unexpected"], ["new.txt"])

    def test_nested_files(self):
        (self.folder / "nested").mkdir()
        (self.folder / "nested" / "data.bin").write_bytes(b"abc")
        self.assertIn("nested/data.bin", inventory(self.folder))

    def test_repeatable_build(self):
        self.assertEqual(build(self.folder, self.manifest),
                         build(self.folder, self.manifest))

    def test_manifest_inside_directory_excluded(self):
        output = self.folder / "manifest.json"
        build(self.folder, output)
        self.assertTrue(check(self.folder, output)["ok"])

    def test_wrong_digest_rejected(self):
        with self.assertRaises(ValueError):
            validate({"version": 1, "algorithm": "sha256",
                      "files": {"data.bin": {"size": 1, "sha256": "wrong"}}})

    def test_relative_path_validation(self):
        with self.assertRaises(ValueError):
            validate({"version": 1, "algorithm": "sha256",
                      "files": {"../outside": {"size": 0, "sha256": "0" * 64}}})

    def test_cli(self):
        app = Path(__file__).resolve().parents[1] / "backup_manifest.py"
        subprocess.run([sys.executable, str(app), "build",
                        str(self.folder), str(self.manifest)], check=True,
                       capture_output=True)
        result = subprocess.run([sys.executable, str(app), "check",
                                 str(self.folder), str(self.manifest)],
                                check=True, capture_output=True, text=True)
        self.assertTrue(json.loads(result.stdout)["ok"])

if __name__ == "__main__":
    unittest.main()
