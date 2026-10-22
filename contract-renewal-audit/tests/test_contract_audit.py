"""Regression tests using synthetic agreements."""

import csv
import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from contract_audit import (FIELDS, DataError, iso_date, money, load_csv,
                            review, save, spreadsheet_safe, summary, main)


TODAY = date(2026, 10, 22)


def make(**changes):
    values = dict(zip(FIELDS, ("A", "Acme Services", "2026-01-01",
                                "2027-12-31", "60", "yes",
                                "1200.50", "USD", "active")))
    values.update(changes)
    return {"line": 2, "data": values, "codes": [], "deadline": None,
            "valid": False, "amount": None}


class FieldTests(unittest.TestCase):
    def test_iso_valid(self):
        self.assertEqual(iso_date("2026-10-22"), TODAY)

    def test_iso_invalid(self):
        for value in ("2026-2-1", "20260201", "2026-02-30", "x"):
            with self.subTest(value=value):
                self.assertIsNone(iso_date(value))

    def test_decimal_preserves_precision(self):
        self.assertEqual(money("0.10"), Decimal("0.10"))

    def test_decimal_invalid(self):
        for value in ("NaN", "Infinity", "-0.01", "not a number", ""):
            with self.subTest(value=value):
                self.assertIsNone(money(value))

    def test_spreadsheet_injection(self):
        for value in ("=A1", " +SUM(A1)", "@danger", "\t-2"):
            with self.subTest(value=value):
                self.assertTrue(spreadsheet_safe(value).startswith("'"))

    def test_safe_vendor_unchanged(self):
        self.assertEqual(spreadsheet_safe("Test Vendor"), "Test Vendor")


class RuleTests(unittest.TestCase):
    def check(self, **changes):
        return review([make(**changes)], TODAY)[0]

    def test_clean_record(self):
        self.assertEqual(self.check()["codes"], [])

    def test_expiring_soon(self):
        self.assertEqual(self.check(end_date="2026-11-01",
                                    auto_renew="no")["codes"], ["EXPIRING_SOON"])

    def test_expired_active(self):
        self.assertEqual(self.check(end_date="2026-10-01")["codes"], ["EXPIRED_ACTIVE"])

    def test_notice_due_soon(self):
        self.assertIn("NOTICE_DUE_SOON",
                      self.check(end_date="2026-12-01", notice_days="30")["codes"])

    def test_notice_deadline_passed(self):
        self.assertIn("NOTICE_DEADLINE_PASSED",
                      self.check(end_date="2026-11-01", notice_days="30")["codes"])

    def test_notice_due_on_today(self):
        self.assertIn("NOTICE_DUE_SOON",
                      self.check(end_date="2026-11-21", notice_days="30")["codes"])

    def test_terminated_no_warnings(self):
        self.assertEqual(self.check(status="terminated",
                                    end_date="2026-10-01")["codes"], [])

    def test_nonrenewal_no_notice(self):
        codes = self.check(auto_renew="no", end_date="2026-11-01")["codes"]
        self.assertNotIn("NOTICE_DEADLINE_PASSED", codes)

    def test_all_invalid_fields(self):
        row = self.check(contract_id="", vendor="", start_date="?", end_date="?",
                         notice_days="-1", auto_renew="?", annual_amount="NaN",
                         currency="US$", status="?")
        self.assertGreaterEqual(len(row["codes"]), 9)

    def test_reversed_dates(self):
        self.assertIn("END_BEFORE_START",
                      self.check(end_date="2025-01-01")["codes"])

    def test_duplicate_every_occurrence(self):
        a, b = make(), make(contract_id=" a ")
        review([a, b], TODAY)
        self.assertIn("DUPLICATE_CONTRACT_ID", a["codes"])
        self.assertIn("DUPLICATE_CONTRACT_ID", b["codes"])

    def test_nonduplicate_empty_identifiers(self):
        a, b = make(contract_id=""), make(contract_id="")
        review([a, b], TODAY)
        self.assertNotIn("DUPLICATE_CONTRACT_ID", a["codes"])

    def test_horizon_zero(self):
        row = review([make(end_date="2026-11-01",
                           auto_renew="no")], TODAY, horizon=0)[0]
        self.assertEqual(row["codes"], [])

    def test_horizon_invalid(self):
        for horizon in (-1, 3651):
            with self.assertRaises(ValueError):
                review([make()], TODAY, horizon)

    def test_cross_currency_not_added(self):
        a = make()
        b = make(contract_id="B", currency="EUR", annual_amount="50.10")
        result = summary(review([a, b], TODAY), TODAY, 30)
        self.assertEqual(result["active_annual_amount_by_currency"],
                         {"EUR": "50.10", "USD": "1200.50"})

    def test_exact_same_currency_sum(self):
        a, b = make(annual_amount="0.10"), make(
            contract_id="B", annual_amount="0.20")
        result = summary(review([a, b], TODAY), TODAY, 30)
        self.assertEqual(result["active_annual_amount_by_currency"]["USD"], "0.30")


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def source(self, records):
        path = self.root / "source.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows([record["data"] for record in records])
        return path

    def test_missing_header(self):
        path = self.root / "source.csv"
        path.write_text("contract_id\nA\n")
        with self.assertRaises(DataError):
            load_csv(path)

    def test_duplicate_header(self):
        path = self.root / "source.csv"
        path.write_text(",".join(FIELDS) + ",vendor\n")
        with self.assertRaises(DataError):
            load_csv(path)

    def test_empty_source(self):
        path = self.root / "empty.csv"
        path.write_text("")
        with self.assertRaises(DataError):
            load_csv(path)

    def test_utf8_bom(self):
        path = self.source([make()])
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.assertEqual(len(load_csv(path)), 1)

    def test_missing_csv_fields(self):
        path = self.root / "source.csv"
        path.write_text(",".join(FIELDS) + "\nA,Vendor\n")
        self.assertIn("MALFORMED_ROW", load_csv(path)[0]["codes"])

    def test_extra_csv_fields(self):
        path = self.source([make()])
        with path.open("a") as stream:
            stream.write("A,Vendor,2026-01-01,2027-12-31,60,yes,20,USD,active,EXTRA\n")
        self.assertIn("MALFORMED_ROW", load_csv(path)[1]["codes"])

    def test_csv_and_json_reports(self):
        records = review([make(end_date="2026-11-01",
                               auto_renew="no"), make(contract_id="B")], TODAY)
        csv_path, json_path = self.root / "out.csv", self.root / "out.json"
        report = save(records, TODAY, 30, csv_path, json_path)
        with csv_path.open(newline="") as stream:
            findings = list(csv.DictReader(stream))
        self.assertEqual(len(findings), 1)
        self.assertEqual(report["rows_flagged"], 1)
        self.assertEqual(json.loads(json_path.read_text())["rows_reviewed"], 2)

    def test_report_formula_protection(self):
        row = make(contract_id="=LINK()", vendor="@cmd", status="?")
        rows = review([row], TODAY)
        path, meta = self.root / "report.csv", self.root / "meta.json"
        save(rows, TODAY, 30, path, meta)
        with path.open(newline="") as stream:
            item = next(csv.DictReader(stream))
        self.assertEqual(item["contract_id"], "'=LINK()")
        self.assertEqual(item["vendor"], "'@cmd")

    def test_conflicting_outputs_rejected(self):
        with self.assertRaises(ValueError):
            save([], TODAY, 30, self.root / "same", self.root / "same")

    def test_cli_complete(self):
        source = self.source([make()])
        status = main([str(source), "--as-of", "2026-10-22",
                       "--findings", str(self.root / "out.csv"),
                       "--summary", str(self.root / "out.json")])
        self.assertEqual(status, 0)

    def test_cli_invalid_date(self):
        with self.assertRaises(SystemExit) as context:
            main([str(self.source([make()])), "--as-of", "bad"])
        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
