import csv
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cleaner import clean_csv


class CleanerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "input.csv"
        self.output = Path(self.temp.name) / "out.csv"

    def test_normalizes_deduplicates_and_filters(self):
        self.source.write_text(
            "id,name,email\n001, Alice , A@example.com \n"
            "002,Bob,b@example.com\n003,ALICE,a@example.com\n"
            ",,\n004,Charlie,\n", encoding="utf-8")
        result = clean_csv(self.source, self.output,
                           required=["email"], dedupe_by=["email"])
        self.assertEqual(result["read"], 5)
        self.assertEqual(result["written"], 2)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["blank"], 1)
        self.assertEqual(result["missing_required"], 1)
        with self.output.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["id"], "001")
        self.assertEqual(rows[0]["name"], "Alice")

    def test_unknown_column_rejected(self):
        self.source.write_text("id,name\n1,Alice\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            clean_csv(self.source, self.output, required=["unknown"])

    def test_duplicate_trimmed_headers_rejected(self):
        self.source.write_text("id, id\n1,2\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            clean_csv(self.source, self.output)

    def test_extra_fields_rejected(self):
        self.source.write_text("id,name\n1,Alice,extra\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            clean_csv(self.source, self.output)


if __name__ == "__main__":
    unittest.main()
