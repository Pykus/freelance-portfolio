import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = "employee_id,store,contracted_hours,worked_hours,overtime_hours,sick_hours,vacation_hours,hourly_rate,bonus\n"
GOOD = "E001,North,160,168,8,0,0,20,0\n"
BAD = "E002,South,160,185,25,0,0,20,0\n"


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "in.csv"
        self.source.write_text(HEADER + GOOD + BAD)
        self.issues = self.folder / "issues.csv"
        self.summary = self.folder / "summary.json"

    def execute(self, *extra):
        return subprocess.run(
            [sys.executable, "-m", "payroll_review", str(self.source),
             "--issues", str(self.issues), "--summary", str(self.summary), *extra],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )

    def test_exit_success(self):
        self.assertEqual(self.execute().returncode, 0)

    def test_json_totals(self):
        self.execute()
        self.assertEqual(json.loads(self.summary.read_text())["issue_rows"], 1)

    def test_issue_row(self):
        self.execute()
        with self.issues.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]["employee_id"], "E002")
        self.assertIn("HIGH_OVERTIME", rows[0]["issue_codes"])

    def test_threshold_override(self):
        result = self.execute("--max-overtime", "7")
        self.assertEqual(json.loads(result.stdout)["issue_rows"], 2)

    def test_invalid_threshold(self):
        self.assertNotEqual(self.execute("--max-overtime", "NaN").returncode, 0)

    def test_does_not_overwrite_source(self):
        result = subprocess.run(
            [sys.executable, "-m", "payroll_review", str(self.source),
             "--issues", str(self.source), "--summary", str(self.summary)],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.source.read_text(), HEADER + GOOD + BAD)
