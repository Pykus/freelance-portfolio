import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from audit import audit_rows, audit_files, main, timestamp

PLAN = {"slot_id": "alpha", "scheduled_at": "2026-10-24T10:00:00+02:00"}
RUN = {"slot_id": "alpha", "started_at": "2026-10-24T10:05:00+02:00", "status": "success"}


def check(plan=None, runs=None, tolerance=15):
    return [i.code for i in audit_rows(plan if plan is not None else [PLAN],
                                       runs if runs is not None else [RUN],
                                       tolerance)]


class RunAuditTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(check(), [])

    def test_absent_run(self):
        self.assertIn("missing_run", check(runs=[]))

    def test_failed(self):
        self.assertIn("unsuccessful_run", check(runs=[dict(RUN, status="failed")]))

    def test_cancelled(self):
        self.assertIn("unsuccessful_run", check(runs=[dict(RUN, status="cancelled")]))

    def test_late(self):
        self.assertIn("late_start", check(runs=[dict(
            RUN, started_at="2026-10-24T10:16:00+02:00")]))

    def test_exact_boundary_is_accepted(self):
        self.assertEqual(check(runs=[dict(
            RUN, started_at="2026-10-24T10:15:00+02:00")]), [])

    def test_offset_comparison(self):
        self.assertEqual(check(runs=[dict(
            RUN, started_at="2026-10-24T08:05:00+00:00")]), [])

    def test_duplicate_plan(self):
        self.assertIn("duplicate_expected", check(plan=[PLAN, PLAN]))

    def test_duplicate_run(self):
        self.assertIn("duplicate_observed", check(runs=[RUN, RUN]))

    def test_unexpected_run(self):
        self.assertIn("unexpected_run", check(plan=[]))

    def test_invalid_plan_date(self):
        self.assertIn("invalid_scheduled_time", check(plan=[
            dict(PLAN, scheduled_at="nope")]))

    def test_invalid_actual_date(self):
        self.assertIn("invalid_started_time", check(runs=[
            dict(RUN, started_at="bad")]))

    def test_missing_offset(self):
        with self.assertRaises(ValueError):
            timestamp("2026-10-24T10:00:00")

    def test_invalid_status(self):
        self.assertIn("invalid_status", check(runs=[dict(RUN, status="unknown")]))

    def test_missing_plan_id(self):
        self.assertIn("invalid_expected_id", check(plan=[dict(PLAN, slot_id="")]))

    def test_missing_run_id(self):
        self.assertIn("invalid_observed_id", check(runs=[dict(RUN, slot_id="")]))

    def test_negative_tolerance(self):
        with self.assertRaises(ValueError):
            audit_rows([], [], -1)

    def test_excess_tolerance(self):
        with self.assertRaises(ValueError):
            audit_rows([], [], 1441)

    def test_empty_inputs(self):
        self.assertEqual(audit_rows([], []), [])

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, run, report = root/"plan.csv", root/"run.csv", root/"report.csv"
            with plan.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(PLAN))
                writer.writeheader()
                writer.writerow(PLAN)
            with run.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(RUN))
                writer.writeheader()
                writer.writerow(dict(RUN, status="failed"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(plan), str(run), str(report)]), 1)
            with report.open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_paths_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"same.csv"
            with self.assertRaises(ValueError):
                audit_files(path, path, path, 15)

    def test_bad_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            a, b, out = root/"a.csv", root/"b.csv", root/"out.csv"
            a.write_text("slot_id\nx\n")
            b.write_text("slot_id,started_at,status\nx,2026-10-24T10:00+02:00,success\n")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(a), str(b), str(out)]), 2)


if __name__ == "__main__":
    unittest.main()
