import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from payroll_review.audit import analyze
from payroll_review.checks import validate_headers
from payroll_review.output import safe_spreadsheet_cell

ROW = {
    "employee_id": "E001", "store": "North", "contracted_hours": "160",
    "worked_hours": "168", "overtime_hours": "8", "sick_hours": "0",
    "vacation_hours": "0", "hourly_rate": "20", "bonus": "0",
}


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "payroll.csv"

    def rows(self, data):
        with self.path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(ROW))
            writer.writeheader()
            writer.writerows(data)
        return analyze(self.path)

    def test_empty_file_data(self):
        self.assertEqual(self.rows([])[2]["total_rows"], 0)

    def test_one_clean(self):
        self.assertEqual(self.rows([ROW])[2]["valid_rows"], 1)

    def test_two_unique(self):
        self.assertEqual(self.rows([ROW, {**ROW, "employee_id": "E002"}])[2]["valid_rows"], 2)

    def test_duplicate_marks_both(self):
        result = self.rows([ROW, {**ROW, "employee_id": " e001 "}])
        self.assertEqual(result[2]["issue_counts"]["DUPLICATE_EMPLOYEE_ID"], 2)

    def test_three_duplicates(self):
        self.assertEqual(self.rows([ROW, ROW, ROW])[2]["issue_rows"], 3)

    def test_custom_overtime(self):
        self.rows([ROW])
        self.assertEqual(analyze(self.path, Decimal(7))[2]["issue_rows"], 1)

    def test_negative_threshold(self):
        self.rows([ROW])
        with self.assertRaises(ValueError):
            analyze(self.path, Decimal(-1))

    def test_missing_header(self):
        self.path.write_text("")
        with self.assertRaisesRegex(ValueError, "Missing CSV header"):
            analyze(self.path)

    def test_missing_column(self):
        with self.assertRaises(ValueError):
            validate_headers(["employee_id"])

    def test_duplicate_header(self):
        with self.assertRaises(ValueError):
            validate_headers(["employee_id", "employee_id"])

    def test_escape_formula(self):
        self.assertEqual(safe_spreadsheet_cell(" =1+2"), "' =1+2")

    def test_safe_text_unchanged(self):
        self.assertEqual(safe_spreadsheet_cell("North"), "North")
