"""Unit and command-line tests, all using generated synthetic images."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit import audit_directory, file_digest, inspect_image, main, write_reports


class ImageAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "incoming"
        self.source.mkdir()

    def make_image(self, relative, size=(600, 400), fmt="PNG"):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (40, 120, 210)).save(path, format=fmt)
        return path

    def test_valid_png(self):
        self.make_image("a.png")
        result = audit_directory(self.source, 400, 300)
        self.assertEqual(result["summary"],
                         {"total": 1, "valid": 1, "duplicate": 0, "too_small": 0, "invalid": 0})
        self.assertEqual(result["records"][0]["width"], 600)
        self.assertEqual(result["records"][0]["format"], "PNG")

    def test_valid_jpeg(self):
        image = self.make_image("photo.jpg", fmt="JPEG")
        self.assertEqual(inspect_image(image), ("JPEG", 600, 400))

    def test_minimum_dimensions_are_inclusive(self):
        self.make_image("boundary.png", (400, 300))
        self.assertEqual(audit_directory(self.source, 400, 300)["summary"]["valid"], 1)

    def test_below_either_minimum_is_too_small(self):
        self.make_image("wide.png", (600, 299))
        self.make_image("tall.png", (399, 500))
        self.assertEqual(audit_directory(self.source, 400, 300)["summary"]["too_small"], 2)

    def test_exact_duplicates_include_reference(self):
        first = self.make_image("a.png")
        (self.source / "b.png").write_bytes(first.read_bytes())
        result = audit_directory(self.source, 400, 300)
        self.assertEqual(result["summary"]["duplicate"], 1)
        self.assertEqual(result["records"][1]["reason"], "Exact duplicate of a.png")

    def test_visually_equal_but_distinct_files_not_called_duplicates(self):
        self.make_image("a.png")
        self.make_image("b.jpg", fmt="JPEG")
        self.assertEqual(audit_directory(self.source, 400, 300)["summary"]["duplicate"], 0)

    def test_truncated_image_is_invalid(self):
        image = self.make_image("cut.png")
        image.write_bytes(image.read_bytes()[:40])
        self.assertEqual(audit_directory(self.source, 400, 300)["summary"]["invalid"], 1)

    def test_mislabeled_image_is_invalid(self):
        jpg = self.make_image("photo.jpg", fmt="JPEG")
        (self.source / "wrong.png").write_bytes(jpg.read_bytes())
        self.assertEqual(audit_directory(self.source, 400, 300)["summary"]["invalid"], 1)

    def test_corrupt_file_is_invalid(self):
        (self.source / "bad.jpg").write_bytes(b"bad")
        row = audit_directory(self.source, 400, 300)["records"][0]
        self.assertEqual(row["status"], "invalid")
        self.assertTrue(row["sha256"])

    def test_nested_paths_sorted_and_unrelated_files_ignored(self):
        self.make_image("z/deep.png")
        self.make_image("a.png", size=(601, 401))
        (self.source / "notes.txt").write_text("ignore me", encoding="utf-8")
        rows = audit_directory(self.source, 400, 300)["records"]
        self.assertEqual([r["path"] for r in rows], ["a.png", "z/deep.png"])

    def test_empty_directory(self):
        self.assertEqual(audit_directory(self.source, 400, 300)["summary"]["total"], 0)

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            audit_directory(self.source, 0, 300)
        with self.assertRaises(ValueError):
            audit_directory(self.root / "absent", 400, 300)
        with self.assertRaises(ValueError):
            write_reports({"records": []}, self.root / "both.csv", self.root / "both.csv")

    def test_symlinks_not_followed(self):
        original = self.make_image("original.png")
        try:
            (self.source / "link.png").symlink_to(original)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported")
        result = audit_directory(self.source, 400, 300)
        self.assertEqual(result["summary"]["invalid"], 1)
        self.assertEqual(result["summary"]["valid"], 1)

    def test_csv_and_json_reports(self):
        self.make_image("a.png")
        result = audit_directory(self.source, 400, 300)
        csv_path = self.root / "out" / "audit.csv"
        json_path = self.root / "out" / "audit.json"
        write_reports(result, csv_path, json_path)
        with csv_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]["path"], "a.png")
        self.assertEqual(rows[0]["status"], "valid")
        self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), result)

    def test_cli(self):
        self.make_image("a.png")
        code = main([str(self.source), "--csv", str(self.root / "audit.csv"),
                     "--json", str(self.root / "audit.json")])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "audit.csv").exists())

    def test_cli_fail_on_invalid(self):
        (self.source / "bad.png").write_bytes(b"not a png")
        script = Path(__file__).resolve().parents[1] / "audit.py"
        process = subprocess.run(
            [sys.executable, str(script), str(self.source),
             "--csv", str(self.root / "audit.csv"),
             "--json", str(self.root / "audit.json"), "--fail-on-invalid"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["invalid"], 1)
        self.assertTrue((self.root / "audit.csv").exists())

    def test_file_hash_matches_known_digest(self):
        path = self.root / "bytes.txt"
        path.write_bytes(b"abc")
        self.assertEqual(file_digest(path),
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


if __name__ == "__main__":
    unittest.main()
