"""Tests for timezone-aware helpdesk response SLAs."""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sla_audit import (audit, main, parse_timestamp, read_policies,
                       read_rows, safe_cell, write_report)

BASE = Path(__file__).resolve().parents[1]
ASOF = datetime.fromisoformat("2026-10-01T14:00:00+00:00")


class TicketSlaTests(unittest.TestCase):
    def setUp(self):
        self.tickets = read_rows(
            BASE / "examples/tickets.csv",
            ("ticket_id", "priority", "state", "opened_at", "first_reply_at"))
        self.policies = read_policies(BASE / "examples/slas.csv")

    def test_summary(self):
        rows, report = audit(self.tickets, self.policies, ASOF)
        self.assertEqual(len(rows), 6)
        self.assertEqual(report, {"total_tickets": 6, "met": 2, "breached": 1,
                                  "breached_open": 1, "pending": 1,
                                  "data_error": 1, "needs_attention": 3})

    def test_each_ticket_outcome(self):
        rows, _ = audit(self.tickets, self.policies, ASOF)
        self.assertEqual({r["ticket_id"]: r["result"] for r in rows},
                         {"T-100": "met", "T-101": "breached",
                          "T-102": "pending", "T-103": "breached_open",
                          "T-104": "met", "T-105": "data_error"})

    def test_boundary_reply_exactly_at_deadline(self):
        rows = [dict(ticket_id="B1", priority="urgent", state="open",
                     opened_at="2026-10-01T10:00:00+00:00",
                     first_reply_at="2026-10-01T11:00:00+00:00")]
        self.assertEqual(audit(rows, {"urgent": 1}, ASOF)[0][0]["result"], "met")

    def test_open_ticket_exactly_at_deadline_pending(self):
        rows = [dict(ticket_id="B2", priority="urgent", state="open",
                     opened_at="2026-10-01T13:00:00+00:00",
                     first_reply_at="")]
        self.assertEqual(audit(rows, {"urgent": 1}, ASOF)[0][0]["result"],
                         "pending")

    def test_timezone_conversion(self):
        self.assertEqual(parse_timestamp("2026-10-01T15:00:00+01:00"), ASOF)
        self.assertEqual(parse_timestamp("2026-10-01T14:00:00Z"), ASOF)

    def test_rejects_naive_timestamp(self):
        with self.assertRaisesRegex(ValueError, "Timezone"):
            parse_timestamp("2026-10-01T14:00:00")

    def test_rejects_invalid_timestamp(self):
        with self.assertRaisesRegex(ValueError, "Invalid ISO"):
            parse_timestamp("someday")

    def test_duplicate_id(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            audit(self.tickets + [self.tickets[0]], self.policies, ASOF)

    def test_unknown_priority(self):
        row = dict(self.tickets[0], priority="not-defined")
        with self.assertRaisesRegex(ValueError, "No SLA policy"):
            audit([row], self.policies, ASOF)

    def test_invalid_state(self):
        row = dict(self.tickets[0], state="unclear")
        with self.assertRaisesRegex(ValueError, "state"):
            audit([row], self.policies, ASOF)

    def test_reply_before_open(self):
        row = dict(self.tickets[0], first_reply_at="2026-10-01T08:00:00Z")
        with self.assertRaisesRegex(ValueError, "Response outside"):
            audit([row], self.policies, ASOF)

    def test_reply_after_report(self):
        row = dict(self.tickets[0], first_reply_at="2026-10-01T15:00:00Z")
        with self.assertRaisesRegex(ValueError, "Response outside"):
            audit([row], self.policies, ASOF)

    def test_ticket_opened_in_future(self):
        row = dict(self.tickets[0], opened_at="2026-10-02T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "after report"):
            audit([row], self.policies, ASOF)

    def test_rejects_naive_report_time(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            audit(self.tickets, self.policies, datetime(2026, 10, 1, 14))

    def test_policy_requires_positive_hours(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.csv"
            for bad in ("0", "-1", "nan", "inf", "oops"):
                path.write_text("priority,reply_within_hours\nurgent," + bad + "\n")
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    read_policies(path)

    def test_duplicate_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.csv"
            path.write_text("priority,reply_within_hours\nurgent,1\nurgent,2\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                read_policies(path)

    def test_bad_csv_columns_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tickets.csv"
            path.write_text("ticket_id,state\nA,open\n")
            with self.assertRaisesRegex(ValueError, "columns"):
                read_rows(path, ("ticket_id", "opened_at"))

    def test_csv_formula_safety(self):
        self.assertEqual(safe_cell("=SUM(1)"), "'=SUM(1)")
        self.assertEqual(safe_cell("normal"), "normal")

    def test_export_and_import_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["--output", tmp]), 0)
            with (Path(tmp) / "ticket-sla.csv").open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 6)
            summary = json.loads((Path(tmp) / "summary.json").read_text())
            self.assertEqual(summary["needs_attention"], 3)

    def test_deterministic_order(self):
        rows, _ = audit(list(reversed(self.tickets)), self.policies, ASOF)
        self.assertEqual([r["ticket_id"] for r in rows],
                         sorted(r["ticket_id"] for r in rows))


if __name__ == "__main__":
    unittest.main()
