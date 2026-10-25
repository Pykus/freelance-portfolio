"""Tests for daily and cumulative campaign budget reconciliation."""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path

from pacing import REQUIRED, audit_file, audit_rows, main, money


def item(**kwargs):
    record = {
        "campaign_id": "A",
        "date": "2026-10-01",
        "budget_usd": "100.00",
        "spend_usd": "90.00",
    }
    record.update(kwargs)
    return record


def issues(*rows):
    return [issue.code for issue in audit_rows(rows).issues]


class PacingTests(unittest.TestCase):
    def test_no_issue(self):
        self.assertEqual(issues(item()), [])

    def test_summary(self):
        s = audit_rows([item()]).summaries[0]
        self.assertEqual((s.budget_usd, s.spend_usd, s.variance_usd),
                         (Decimal("100"), Decimal("90"), Decimal("10")))
        self.assertEqual(s.utilization_pct, Decimal("90.00"))

    def test_exact_budget(self):
        self.assertEqual(issues(item(spend_usd="100")), [])

    def test_daily_overspend(self):
        self.assertIn("daily_overspend", issues(item(spend_usd="101")))

    def test_cumulative_overspend(self):
        self.assertIn("cumulative_overspend", issues(item(spend_usd="101")))

    def test_smoothing_over_multiple_days(self):
        result = audit_rows([
            item(date="2026-10-01", spend_usd="40"),
            item(date="2026-10-02", spend_usd="140"),
        ])
        self.assertEqual([i.code for i in result.issues], ["daily_overspend"])
        self.assertEqual(result.summaries[0].spend_usd, Decimal("180"))

    def test_cumulative_after_previous_excess(self):
        self.assertIn("cumulative_overspend", issues(
            item(date="2026-10-01", spend_usd="150"),
            item(date="2026-10-02", spend_usd="60"),
        ))

    def test_sort_dates_instead_of_row_order(self):
        result = audit_rows([
            item(date="2026-10-02", spend_usd="100"),
            item(date="2026-10-01", spend_usd="0"),
        ])
        self.assertEqual(result.summaries[0].days, 2)
        self.assertEqual(result.summaries[0].spend_usd, Decimal("100"))
        self.assertEqual(result.issues, [])

    def test_independent_campaigns(self):
        r = audit_rows([item(campaign_id="B"), item(campaign_id="A")])
        self.assertEqual([s.campaign_id for s in r.summaries], ["a", "b"])

    def test_duplicate_case_insensitive(self):
        r = audit_rows([item(campaign_id="ABC"), item(campaign_id="abc")])
        self.assertEqual([i.code for i in r.issues], ["duplicate_day"])
        self.assertEqual(len(r.summaries), 1)
        self.assertEqual(r.summaries[0].days, 1)

    def test_missing_field(self):
        self.assertIn("missing_field", issues(item(campaign_id="")))

    def test_bad_date(self):
        self.assertIn("invalid_date", issues(item(date="2026-02-30")))

    def test_bad_budget(self):
        self.assertIn("invalid_amount", issues(item(budget_usd="0")))

    def test_negative_spend(self):
        self.assertIn("invalid_amount", issues(item(spend_usd="-1")))

    def test_fractional_cent(self):
        self.assertIn("invalid_amount", issues(item(spend_usd="1.001")))

    def test_nan(self):
        with self.assertRaises(ValueError):
            money("NaN")

    def test_overflowish_amount(self):
        with self.assertRaises(ValueError):
            money("Infinity")

    def test_empty_rows(self):
        self.assertEqual(audit_rows([]).summaries, [])
        self.assertEqual(audit_rows([]).issues, [])

    def test_cli_and_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp, report, summary = (root / name for name in ("daily.csv", "issues.csv", "summary.csv"))
            with inp.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=REQUIRED)
                writer.writeheader()
                writer.writerow(item(spend_usd="150"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(inp), str(report), str(summary)]), 1)
            with report.open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 2)
            with summary.open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_missing_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            inp = Path(directory) / "in.csv"
            inp.write_text("date,spend_usd\n2026-10-01,1\n")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(inp), str(inp.parent / "i.csv"),
                                       str(inp.parent / "s.csv")]), 2)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            inp = Path(directory) / "in.csv"
            inp.write_text(",".join(REQUIRED) + "\n")
            with self.assertRaises(ValueError):
                audit_file(inp, inp, Path(directory) / "s.csv")


if __name__ == "__main__":
    unittest.main()
