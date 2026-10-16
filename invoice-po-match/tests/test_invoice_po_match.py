"""Unit and end-to-end tests for deterministic invoice matching."""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from invoice_po_match import DataError, audit, fmt, money_to_cents, parse_items, parse_orders, save


def po(**changes):
    sample = {"po_id": "PO-1", "supplier": "Sample Supplies", "currency": "USD",
              "items": [{"sku": "A", "quantity": 4, "unit_price": "12.50"}]}
    return {**sample, **changes}


def inv(**changes):
    sample = {"invoice_id": "INV-1", "po_id": "PO-1",
              "supplier": "Sample Supplies", "currency": "USD",
              "items": [{"sku": "A", "quantity": 2, "unit_price": "12.50"}],
              "claimed_subtotal": "25.00", "tax": "2.00", "claimed_total": "27.00"}
    return {**sample, **changes}


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.orders = parse_orders([po()])

    def issue_codes(self, **changes):
        return audit([inv(**changes)], self.orders)[0]["issues"]

    def test_integer_cents_are_exact(self):
        self.assertEqual(money_to_cents("19.90", "price"), 1990)
        self.assertEqual(money_to_cents("0", "price"), 0)
        self.assertEqual(fmt(1209), "12.09")

    def test_invalid_prices_rejected(self):
        for value in (1.5, "-1", "1.001", "NaN", "1e2", ""):
            with self.subTest(value=value), self.assertRaises(DataError):
                money_to_cents(value, "price")

    def test_duplicate_sku_rejected(self):
        with self.assertRaises(DataError):
            parse_items([{"sku": "A", "quantity": 1, "unit_price": "1.00"},
                         {"sku": "A", "quantity": 2, "unit_price": "1.00"}], "items")

    def test_boolean_quantity_is_not_integer(self):
        with self.assertRaises(DataError):
            parse_items([{"sku": "A", "quantity": True, "unit_price": "1"}], "items")

    def test_valid_invoice_is_ready(self):
        row = audit([inv()], self.orders)[0]
        self.assertEqual((row["status"], row["computed_subtotal"]), ("READY", "25.00"))

    def test_unknown_purchase_order(self):
        self.assertIn("PO_NOT_FOUND", self.issue_codes(po_id="OTHER"))

    def test_supplier_and_currency_differ(self):
        self.assertEqual(self.issue_codes(supplier="Elsewhere", currency="EUR"),
                         ["CURRENCY_MISMATCH", "SUPPLIER_MISMATCH"])

    def test_unknown_sku(self):
        self.assertIn("UNKNOWN_SKU", self.issue_codes(items=[
            {"sku": "B", "quantity": 1, "unit_price": "25.00"}]))

    def test_excessive_quantity(self):
        self.assertIn("QUANTITY_EXCEEDS_ORDER", self.issue_codes(
            items=[{"sku": "A", "quantity": 5, "unit_price": "12.50"}],
            claimed_subtotal="62.50", claimed_total="64.50"))

    def test_unit_price_mismatch(self):
        self.assertIn("UNIT_PRICE_MISMATCH", self.issue_codes(
            items=[{"sku": "A", "quantity": 2, "unit_price": "11.50"}],
            claimed_subtotal="23.00", claimed_total="25.00"))

    def test_wrong_totals(self):
        self.assertEqual(self.issue_codes(claimed_subtotal="24.00", claimed_total="27.01"),
                         ["SUBTOTAL_MISMATCH", "TOTAL_MISMATCH"])

    def test_duplicate_invoice_detected(self):
        rows = audit([inv(), inv()], self.orders)
        self.assertEqual([x["status"] for x in rows], ["READY", "REVIEW"])
        self.assertEqual(rows[1]["issues"], ["DUPLICATE_INVOICE"])

    def test_bad_invoice_does_not_abort_batch(self):
        rows = audit([{"invoice_id": "BROKEN"}, inv()], self.orders)
        self.assertEqual(rows[0]["issues"], ["INVALID_RECORD"])
        self.assertEqual(rows[1]["status"], "READY")

    def test_duplicate_po_rejected(self):
        with self.assertRaises(DataError):
            parse_orders([po(), po()])

    def test_reports_have_deterministic_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = save(audit([inv(), inv(invoice_id="INV-2", po_id="X")],
                                 self.orders), tmp)
            self.assertEqual(summary, {"total": 2, "ready": 1, "review": 1})
            with (Path(tmp) / "invoice_report.csv").open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[1]["issues"], "PO_NOT_FOUND")
            self.assertEqual(json.loads((Path(tmp) / "invoice_report.json").read_text())
                             ["summary"], summary)

    def test_example_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([
                sys.executable, str(ROOT / "invoice_po_match.py"),
                "--orders", str(ROOT / "examples" / "purchase_orders.json"),
                "--invoices", str(ROOT / "examples" / "invoices.json"),
                "--output-dir", tmp,
            ], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout),
                             {"total": 3, "ready": 1, "review": 2})
            self.assertTrue((Path(tmp) / "invoice_report.csv").exists())

    def test_cli_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([
                sys.executable, str(ROOT / "invoice_po_match.py"),
                "--orders", str(Path(tmp) / "missing.json"),
                "--invoices", str(ROOT / "examples" / "invoices.json"),
                "--output-dir", tmp,
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Input/output error", result.stderr)


if __name__ == "__main__":
    unittest.main()
