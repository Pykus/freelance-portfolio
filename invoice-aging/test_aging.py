import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from aging import summarize

class AgingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "invoices.csv"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows):
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["invoice_id", "due_date", "amount"])
            writer.writerows(rows)

    def test_buckets_and_total(self):
        self.write([["001", "2026-10-14", "10.00"], ["002", "2026-10-01", "20.25"],
                    ["003", "2026-08-01", "30.00"], ["004", "2026-06-01", "40.00"]])
        result = summarize(str(self.path), date(2026, 10, 13))
        self.assertEqual(result["total"], "100.25")
        self.assertEqual(result["buckets"]["current"], "10.00")
        self.assertEqual(result["buckets"]["1-30"], "20.25")
        self.assertEqual(result["buckets"]["61-90"], "30.00")
        self.assertEqual(result["buckets"]["90+"], "40.00")

    def test_duplicate_rejected(self):
        self.write([["001", "2026-10-01", "1.00"], ["001", "2026-10-02", "2.00"]])
        with self.assertRaises(ValueError):
            summarize(str(self.path), date(2026, 10, 13))

    def test_invalid_precision_rejected(self):
        self.write([["001", "2026-10-01", "1.001"]])
        with self.assertRaises(ValueError):
            summarize(str(self.path), date(2026, 10, 13))

if __name__ == "__main__":
    unittest.main()
