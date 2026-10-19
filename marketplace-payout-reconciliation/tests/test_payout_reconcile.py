"""Regression tests for marketplace payout audit using fictional statements."""
import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from payout_reconcile import (
    export, main, money, read_records, reconcile, safe_cell,
)
from generate_demo import generate


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.orders_path, self.payouts_path = generate(Path(temporary.name))
        self.orders = read_records(self.orders_path, kind="orders")
        self.payouts = read_records(self.payouts_path, kind="payouts")

    def test_sample_summary(self):
        rows, summary = reconcile(self.orders, self.payouts)
        self.assertEqual(summary, {
            "total": 6, "matched": 2, "amount_mismatch": 1,
            "missing_payout": 1, "orphan_payout": 1, "currency_mismatch": 1,
        })
        self.assertEqual([row["order_id"] for row in rows],
                         ["sample1", "sample2", "sample3", "sample4",
                          "sample5", "sample999"])

    def test_exact_money_and_underpayment(self):
        rows, _ = reconcile(self.orders, self.payouts)
        underpayment = next(row for row in rows if row["order_id"] == "sample2")
        self.assertEqual(underpayment["expected_net"], "66.00")
        self.assertEqual(underpayment["paid_net"], "65.90")
        self.assertEqual(underpayment["difference"], "-0.10")
        self.assertEqual(underpayment["status"], "amount_mismatch")

    def test_matched_and_missing(self):
        rows, _ = reconcile(self.orders, self.payouts)
        by_id = {row["order_id"]: row for row in rows}
        self.assertEqual(by_id["sample1"]["expected_net"], "95.00")
        self.assertEqual(by_id["sample1"]["difference"], "0.00")
        self.assertEqual(by_id["sample1"]["status"], "matched")
        self.assertEqual(by_id["sample4"]["status"], "missing_payout")
        self.assertEqual(by_id["sample4"]["paid_net"], "")

    def test_orphan_payout(self):
        rows, _ = reconcile(self.orders, self.payouts)
        orphan = next(row for row in rows if row["order_id"] == "sample999")
        self.assertEqual(orphan["status"], "orphan_payout")
        self.assertEqual(orphan["expected_net"], "")
        self.assertEqual(orphan["paid_net"], "5.00")

    def test_currency_mismatch_has_no_arithmetic(self):
        rows, _ = reconcile(self.orders, self.payouts)
        mismatch = next(row for row in rows if row["order_id"] == "sample3")
        self.assertEqual(mismatch["status"], "currency_mismatch")
        self.assertEqual(mismatch["payout_currency"], "GBP")
        self.assertEqual(mismatch["currency"], "EUR")
        self.assertEqual(mismatch["difference"], "")

    def test_boundary_tolerance(self):
        rows, counts = reconcile(self.orders, self.payouts, Decimal("0.10"))
        self.assertEqual(counts["matched"], 3)
        self.assertEqual(counts["amount_mismatch"], 0)
        self.assertEqual(next(x for x in rows if x["order_id"] == "sample2")["difference"],
                         "-0.10")

    def test_tolerance_below_difference(self):
        _, counts = reconcile(self.orders, self.payouts, Decimal("0.09"))
        self.assertEqual(counts["amount_mismatch"], 1)

    def test_invalid_tolerance(self):
        for value in (Decimal("-0.01"), Decimal("0.001"), Decimal("NaN")):
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                reconcile(self.orders, self.payouts, value)

    def test_cent_precision(self):
        self.assertEqual(money("0.10") + money("0.20"), Decimal("0.30"))
        self.assertEqual(money("1.000"), Decimal("1.00"))

    def test_invalid_money(self):
        for value in ("not-money", "NaN", "Infinity", "10.003", "-1.00", "1e99999"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                money(value)

    def test_negative_payout_is_permitted(self):
        self.assertEqual(money("-1.25", signed=True), Decimal("-1.25"))

    def test_signed_negative_difference(self):
        payouts = dict(self.payouts)
        payouts["sample1"] = dict(payouts["sample1"], net_paid=Decimal("94.99"))
        rows, _ = reconcile(self.orders, payouts)
        self.assertEqual(rows[0]["difference"], "-0.01")

    def test_order_duplicates_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "duplicate.csv"
            file.write_text(
                "order_id,currency,gross,refund,fee\n"
                "alpha,USD,10.00,0.00,1.00\n"
                "alpha,USD,11.00,0.00,1.00\n")
            with self.assertRaisesRegex(ValueError, "repeated order ID"):
                read_records(file, kind="orders")

    def test_payout_duplicates_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "duplicate.csv"
            file.write_text(
                "order_id,currency,net_paid\n"
                "alpha,USD,1.00\nalpha,USD,2.00\n")
            with self.assertRaisesRegex(ValueError, "repeated order ID"):
                read_records(file, kind="payouts")

    def test_refund_greater_than_gross_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "bad.csv"
            file.write_text(
                "order_id,currency,gross,refund,fee\n"
                "alpha,USD,9.00,10.00,1.00\n")
            with self.assertRaisesRegex(ValueError, "refund exceeds gross"):
                read_records(file, kind="orders")

    def test_missing_columns_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "bad.csv"
            file.write_text("order_id,currency\nalpha,USD\n")
            with self.assertRaisesRegex(ValueError, "required CSV columns"):
                read_records(file, kind="payouts")

    def test_extra_columns_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "bad.csv"
            file.write_text("order_id,currency,net_paid\nalpha,USD,3.00,EXTRA\n")
            with self.assertRaisesRegex(ValueError, "extra CSV field"):
                read_records(file, kind="payouts")

    def test_missing_id_or_invalid_currency(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "bad.csv"
            for bad in ("alpha,usd,3.00", ",USD,3.00"):
                file.write_text("order_id,currency,net_paid\n" + bad + "\n")
                with self.assertRaisesRegex(ValueError, "invalid order ID or currency"):
                    read_records(file, kind="payouts")

    def test_neutralizes_formula_like_identifier(self):
        self.assertEqual(safe_cell("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(safe_cell("ordinary"), "ordinary")
        row = {
            "order_id": "=1+1", "currency": "USD", "payout_currency": "USD",
            "gross": "5.00",
            "refund": "0.00", "fee": "0.00", "expected_net": "5.00",
            "paid_net": "5.00", "difference": "0.00", "status": "matched",
        }
        with tempfile.TemporaryDirectory() as folder:
            export([row], {"total": 1}, Path(folder))
            with (Path(folder) / "reconciliation.csv").open(newline="") as inp:
                self.assertEqual(next(csv.DictReader(inp))["order_id"], "'=1+1")

    def test_empty_files_return_zero_count(self):
        rows, counts = reconcile({}, {})
        self.assertEqual(rows, [])
        self.assertEqual(counts["total"], 0)
        self.assertEqual(counts["matched"], 0)

    def test_full_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            code = main([
                "--orders", str(self.orders_path),
                "--payouts", str(self.payouts_path),
                "--output", folder,
            ])
            self.assertEqual(code, 0)
            summary = json.loads((Path(folder) / "summary.json").read_text())
            self.assertEqual(summary["total"], 6)
            with (Path(folder) / "reconciliation.csv").open(newline="") as inp:
                self.assertEqual(len(list(csv.DictReader(inp))), 6)

    def test_export_is_deterministic(self):
        rows, counts = reconcile(self.orders, self.payouts)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            export(rows, counts, output)
            before = (output / "reconciliation.csv").read_bytes()
            export(rows, counts, output)
            self.assertEqual((output / "reconciliation.csv").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
