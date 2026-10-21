"""Synthetic regression tests for the offline booking auditor."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from booking_audit import SchemaError, audit_csv, export_reports
from booking_audit.__main__ import main

FIELDS = ("booking_id", "resource_id", "start_at", "end_at", "status")
START = "2026-11-02T09:00:00+01:00"
END = "2026-11-02T10:00:00+01:00"


def booking(booking_id="a", resource_id="room", start_at=START, end_at=END,
            status="confirmed"):
    return dict(zip(FIELDS, (booking_id, resource_id, start_at, end_at, status)))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "input.csv"

    def write(self, records, fields=FIELDS):
        with self.path.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
        return self.path

    def run_audit(self, records):
        return audit_csv(self.write(records))

    def codes(self, report):
        return [i.code for i in report.issues]

    def test_overlap_and_exact_seconds(self):
        result = self.run_audit([booking(), booking("b", start_at="2026-11-02T09:30:00+01:00")])
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0].overlap_seconds, 1800)

    def test_adjacent_intervals_do_not_conflict(self):
        result = self.run_audit([booking(), booking("b", start_at=END, end_at="2026-11-02T11:00:00+01:00")])
        self.assertEqual(len(result.conflicts), 0)

    def test_different_resources_do_not_conflict(self):
        result = self.run_audit([booking(), booking("b", resource_id="other")])
        self.assertEqual(len(result.conflicts), 0)

    def test_resource_comparison_is_case_insensitive(self):
        result = self.run_audit([booking(resource_id=" Room "), booking("b", resource_id="ROOM")])
        self.assertEqual(len(result.conflicts), 1)

    def test_nested_intervals_report_every_pair(self):
        result = self.run_audit([
            booking("outer", end_at="2026-11-02T12:00:00+01:00"),
            booking("middle", start_at="2026-11-02T09:30:00+01:00", end_at="2026-11-02T11:00:00+01:00"),
            booking("inner", start_at="2026-11-02T09:45:00+01:00", end_at="2026-11-02T10:15:00+01:00"),
        ])
        self.assertEqual(len(result.conflicts), 3)

    def test_expired_intervals_are_evicted(self):
        result = self.run_audit([
            booking("a"),
            booking("b", start_at="2026-11-02T10:00:00+01:00", end_at="2026-11-02T11:00:00+01:00"),
            booking("c", start_at="2026-11-02T10:30:00+01:00", end_at="2026-11-02T11:15:00+01:00"),
        ])
        self.assertEqual([(c.first.booking_id, c.second.booking_id) for c in result.conflicts], [("b", "c")])

    def test_different_offsets_are_same_instant(self):
        result = self.run_audit([booking(), booking("b", start_at="2026-11-02T08:30:00Z", end_at="2026-11-02T09:30:00Z")])
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0].start.isoformat(), "2026-11-02T08:30:00+00:00")

    def test_cancelled_reservation_is_excluded(self):
        result = self.run_audit([booking(), booking("b", status="cancelled")])
        self.assertEqual(len(result.conflicts), 0)
        self.assertEqual(result.cancelled_bookings, 1)
        self.assertEqual(result.validated_bookings, 1)

    def test_naive_datetime_is_rejected(self):
        result = self.run_audit([booking(start_at="2026-11-02T09:00:00")])
        self.assertIn("INVALID_START_AT", self.codes(result))

    def test_malformed_datetime_is_rejected(self):
        result = self.run_audit([booking(end_at="not-a-date")])
        self.assertIn("INVALID_END_AT", self.codes(result))

    def test_nonpositive_duration_is_rejected(self):
        result = self.run_audit([booking(end_at=START)])
        self.assertIn("NONPOSITIVE_DURATION", self.codes(result))

    def test_end_before_start_is_rejected(self):
        result = self.run_audit([booking(end_at="2026-11-02T08:00:00+01:00")])
        self.assertIn("NONPOSITIVE_DURATION", self.codes(result))

    def test_unknown_status_is_rejected(self):
        result = self.run_audit([booking(status="pending")])
        self.assertIn("INVALID_STATUS", self.codes(result))

    def test_missing_booking_id_is_rejected(self):
        result = self.run_audit([booking(booking_id=" ")])
        self.assertIn("MISSING_BOOKING_ID", self.codes(result))

    def test_missing_resource_is_rejected(self):
        result = self.run_audit([booking(resource_id="")])
        self.assertIn("MISSING_RESOURCE_ID", self.codes(result))

    def test_duplicate_ids_both_flagged_and_excluded(self):
        result = self.run_audit([booking(" a "), booking("A")])
        self.assertEqual(self.codes(result), ["DUPLICATE_BOOKING_ID"] * 2)
        self.assertEqual(result.validated_bookings, 0)
        self.assertEqual(len(result.conflicts), 0)

    def test_duplicate_id_can_cross_resources(self):
        result = self.run_audit([booking("A"), booking("a", resource_id="other")])
        self.assertEqual(result.summary()["invalid_rows"], 2)

    def test_invalid_row_not_compared_with_good_row(self):
        result = self.run_audit([booking(), booking("b", start_at="bad")])
        self.assertEqual(len(result.conflicts), 0)
        self.assertEqual(result.validated_bookings, 1)

    def test_empty_file_is_schema_error(self):
        self.path.write_text("", encoding="utf-8")
        with self.assertRaises(SchemaError):
            audit_csv(self.path)

    def test_missing_header_is_schema_error(self):
        self.path.write_text("booking_id,resource_id\n", encoding="utf-8")
        with self.assertRaisesRegex(SchemaError, "Missing columns"):
            audit_csv(self.path)

    def test_duplicate_header_is_schema_error(self):
        self.path.write_text("booking_id,booking_id,resource_id,start_at,end_at,status\n", encoding="utf-8")
        with self.assertRaisesRegex(SchemaError, "Repeated"):
            audit_csv(self.path)

    def test_header_with_bom(self):
        self.path.write_text("\ufeff" + ",".join(FIELDS) + "\n" + ",".join(booking().values()) + "\n", encoding="utf-8")
        self.assertEqual(audit_csv(self.path).validated_bookings, 1)

    def test_extra_named_columns_are_allowed(self):
        record = booking()
        record["note"] = "synthetic"
        self.write([record], fields=FIELDS + ("note",))
        self.assertEqual(audit_csv(self.path).validated_bookings, 1)

    def test_missing_data_cells_are_reported(self):
        self.path.write_text(",".join(FIELDS) + "\na,room," + START + "\n", encoding="utf-8")
        self.assertIn("MALFORMED_ROW", self.codes(audit_csv(self.path)))

    def test_extra_unnamed_data_cells_are_reported(self):
        self.path.write_text(",".join(FIELDS) + "\n" + ",".join(booking().values()) + ",extra\n", encoding="utf-8")
        self.assertIn("MALFORMED_ROW", self.codes(audit_csv(self.path)))

    def test_summary_counts_issue_types(self):
        result = self.run_audit([booking(), booking("b", end_at=START)])
        self.assertEqual(result.summary()["issue_counts"], {"NONPOSITIVE_DURATION": 1})
        self.assertEqual(result.summary()["input_rows"], 2)
        self.assertEqual(result.summary()["invalid_rows"], 1)

    def test_conflicts_are_deterministically_ordered(self):
        data = [booking("c", resource_id="b"), booking("d", resource_id="b"),
                booking("a", resource_id="a"), booking("b", resource_id="a")]
        self.assertEqual([c.first.resource_id for c in self.run_audit(data).conflicts], ["a", "b"])

    def test_report_files_and_json(self):
        audit = self.run_audit([booking(), booking("b")])
        root = Path(self.temp.name)
        export_reports(audit, root / "conflicts.csv", root / "issues.csv", root / "summary.json", input_file=self.path)
        summary = json.loads((root / "summary.json").read_text())
        self.assertEqual(summary["conflict_pairs"], 1)
        with (root / "conflicts.csv").open(newline="") as file:
            self.assertEqual(len(list(csv.DictReader(file))), 1)

    def test_spreadsheet_formula_injection_is_escaped(self):
        audit = self.run_audit([booking(booking_id="=HYPERLINK('x')"), booking("safe")])
        root = Path(self.temp.name)
        export_reports(audit, root / "a.csv", root / "b.csv", root / "c.json")
        with (root / "a.csv").open(newline="") as file:
            record = next(csv.DictReader(file))
            self.assertTrue(record["first_booking_id"].startswith("'="))

    def test_output_paths_must_be_distinct(self):
        result = self.run_audit([booking()])
        with self.assertRaisesRegex(ValueError, "distinct"):
            export_reports(result, "same.csv", "same.csv", "summary.json")

    def test_input_is_not_overwritten(self):
        result = self.run_audit([booking()])
        with self.assertRaisesRegex(ValueError, "overwrite"):
            export_reports(result, self.path, "other.csv", "summary.json", input_file=self.path)

    def test_cli_end_to_end(self):
        self.write([booking(), booking("b")])
        root = Path(self.temp.name)
        code = main([str(self.path), "--conflicts", str(root / "c.csv"),
                     "--issues", str(root / "i.csv"), "--summary", str(root / "s.json")])
        self.assertEqual(code, 0)
        self.assertTrue((root / "s.json").exists())


if __name__ == "__main__":
    unittest.main()
