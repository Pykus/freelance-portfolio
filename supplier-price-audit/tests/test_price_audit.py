"""Regression tests for exact supplier-price reconciliation."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from price_audit import Product, audit, load_catalog, main, money, safe_excel_cell, write_report

ROOT = Path(__file__).resolve().parents[1]


def product(sku="A", currency="USD", cost="10.00", price="15.00"):
    return Product(sku, currency, Decimal(cost), Decimal(price))


class SupplierPriceAuditTests(unittest.TestCase):
    def setUp(self):
        self.before = load_catalog(ROOT / "examples/before.csv")
        self.after = load_catalog(ROOT / "examples/after.csv")

    def test_worked_example_statuses(self):
        rows, summary = audit(self.before, self.after)
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            [row["status"] for row in rows],
            ["changed", "unchanged", "removed", "changed", "changed", "added"])
        self.assertEqual(summary["total_skus"], 6)
        self.assertEqual(summary["changed"], 3)
        self.assertEqual(summary["unchanged"], 1)
        self.assertEqual(summary["removed"], 1)
        self.assertEqual(summary["added"], 1)

    def test_exact_cost_increase_and_margin(self):
        rows, _ = audit(self.before, self.after)
        first = next(row for row in rows if row["sku"] == "SKU-100")
        self.assertEqual(first["cost_change_percent"], "25.00")
        self.assertEqual(first["gross_margin_percent"], "16.67")
        self.assertIn("cost_increase_over_limit", first["flags"])
        self.assertIn("margin_below_target", first["flags"])

    def test_currency_mismatch_not_calculated_as_fx_growth(self):
        rows, _ = audit(self.before, self.after)
        product = next(row for row in rows if row["sku"] == "SKU-500")
        self.assertEqual(product["old_currency"], "USD")
        self.assertEqual(product["new_currency"], "EUR")
        self.assertEqual(product["cost_change_percent"], "")
        self.assertIn("currency_changed", product["flags"])

    def test_added_product_below_cost(self):
        rows, _ = audit(self.before, self.after)
        product = next(row for row in rows if row["sku"] == "SKU-600")
        self.assertEqual(product["status"], "added")
        self.assertIn("price_below_cost", product["flags"])
        self.assertEqual(product["gross_margin_percent"], "-11.11")

    def test_removed_product_has_no_current_margin(self):
        rows, _ = audit(self.before, self.after)
        removed = next(row for row in rows if row["sku"] == "SKU-300")
        self.assertEqual(removed["status"], "removed")
        self.assertEqual(removed["new_unit_cost"], "")
        self.assertEqual(removed["gross_margin_percent"], "")
        self.assertEqual(removed["flags"], "")

    def test_cost_from_zero_flag(self):
        rows, _ = audit(self.before, self.after)
        item = next(row for row in rows if row["sku"] == "SKU-400")
        self.assertIn("cost_from_zero", item["flags"])
        self.assertEqual(item["cost_change_percent"], "")

    def test_summary_flag_counts(self):
        _, s = audit(self.before, self.after)
        self.assertEqual(s["flag_cost_increase_over_limit"], 1)
        self.assertEqual(s["flag_margin_below_target"], 2)
        self.assertEqual(s["flag_price_below_cost"], 1)
        self.assertEqual(s["flag_currency_changed"], 1)
        self.assertEqual(s["flag_cost_from_zero"], 1)
        self.assertEqual(s["flag_zero_retail_price"], 0)

    def test_equal_threshold_is_not_flagged(self):
        before = {"A": product()}
        after = {"A": product(cost="11.00")}
        rows, _ = audit(before, after, max_cost_increase=Decimal("10"))
        self.assertNotIn("cost_increase_over_limit", rows[0]["flags"])
        rows, _ = audit(before, after, max_cost_increase=Decimal("9.99"))
        self.assertIn("cost_increase_over_limit", rows[0]["flags"])

    def test_zero_retail_price_is_explicit(self):
        rows, _ = audit({}, {"A": product(cost="0.00", price="0.00")})
        self.assertIn("zero_retail_price", rows[0]["flags"])
        self.assertEqual(rows[0]["gross_margin_percent"], "")

    def test_empty_catalogs_produce_empty_report(self):
        rows, summary = audit({}, {})
        self.assertEqual(rows, [])
        self.assertEqual(summary["total_skus"], 0)

    def test_empty_threshold_and_invalid_margin_rejected(self):
        for value in ("NaN", "-1", "Infinity"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    audit({}, {}, max_cost_increase=Decimal(value))
        for value in ("-1", "101", "NaN", "Infinity"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    audit({}, {}, min_margin=Decimal(value))

    def test_decimals_use_exact_arithmetic(self):
        self.assertEqual(money("0.10", source="x", row=2, field="cost")
                         + money("0.20", source="x", row=3, field="cost"),
                         Decimal("0.30"))

    def test_rejects_nonmonetary_input(self):
        for text in ("-1", "NaN", "Infinity", "1.001", "oops", "1000000000001"):
            with self.subTest(value=text):
                with self.assertRaises(ValueError):
                    money(text, source="test.csv", row=2, field="unit_cost")

    def test_duplicate_sku_is_a_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "list.csv"
            p.write_text(
                "sku,currency,unit_cost,retail_price\nA,USD,1,2\nA,USD,2,3\n")
            with self.assertRaisesRegex(ValueError, "repeated SKU"):
                load_catalog(p)

    def test_invalid_currency_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "list.csv"
            p.write_text("sku,currency,unit_cost,retail_price\nA,usd,1,2\n")
            with self.assertRaisesRegex(ValueError, "currency"):
                load_catalog(p)

    def test_missing_column_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "list.csv"
            p.write_text("sku,currency,unit_cost\nA,USD,1\n")
            with self.assertRaisesRegex(ValueError, "CSV needs"):
                load_catalog(p)

    def test_blank_sku_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "list.csv"
            p.write_text("sku,currency,unit_cost,retail_price\n,USD,1,2\n")
            with self.assertRaisesRegex(ValueError, "SKU missing"):
                load_catalog(p)

    def test_formula_like_export_cell_neutralized(self):
        self.assertEqual(safe_excel_cell("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(safe_excel_cell(" +2+2"), "' +2+2")
        self.assertEqual(safe_excel_cell("SKU-100"), "SKU-100")

    def test_full_cli_outputs_auditable_files(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(main(["--output", folder]), 0)
            csv_file = Path(folder) / "price_review.csv"
            self.assertTrue(csv_file.is_file())
            with csv_file.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 6)
            self.assertIn("gross_margin_percent", rows[0])
            summary = json.loads((Path(folder) / "summary.json").read_text())
            self.assertEqual(summary["total_skus"], 6)

    def test_write_report_removes_spreadsheet_formulas(self):
        rows, summary = audit({"=1+1": product("=1+1")}, {})
        with tempfile.TemporaryDirectory() as folder:
            write_report(rows, summary, Path(folder))
            with (Path(folder) / "price_review.csv").open(newline="") as handle:
                self.assertEqual(next(csv.DictReader(handle))["sku"], "'=1+1")

    def test_repeating_run_is_deterministic(self):
        a, sa = audit(self.before, self.after)
        b, sb = audit(self.before, self.after)
        self.assertEqual(a, b)
        self.assertEqual(sa, sb)


if __name__ == "__main__":
    unittest.main()
