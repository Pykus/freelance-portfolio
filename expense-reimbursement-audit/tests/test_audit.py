"""Regression tests for reimbursement auditing."""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from audit import FIELDS, audit_claims, audit_file, main


def claim(**updates):
    row = {
        "claim_id": "C-001",
        "employee_id": "E-001",
        "receipt_id": "R-001",
        "date": "2026-10-01",
        "category": "meals",
        "currency": "USD",
        "amount": "20.00",
    }
    row.update(updates)
    return row


def codes(*rows):
    return [issue.code for issue in audit_claims(rows)]


class AuditTests(unittest.TestCase):
    def test_valid_claim(self):
        self.assertEqual(codes(claim()), [])

    def test_policy_boundary(self):
        self.assertEqual(codes(claim(amount="35.00")), [])

    def test_above_limit(self):
        self.assertIn("exceeds_policy_limit", codes(claim(amount="35.01")))

    def test_invalid_category(self):
        self.assertIn("unknown_category", codes(claim(category="other")))

    def test_casefolded_categories(self):
        self.assertEqual(codes(claim(category="Meals")), [])

    def test_missing_receipt(self):
        self.assertIn("missing_field", codes(claim(receipt_id="")))

    def test_missing_employee(self):
        self.assertIn("missing_field", codes(claim(employee_id="")))

    def test_duplicate_receipt_case_insensitive(self):
        issues = audit_claims([claim(), claim(claim_id="C-002", receipt_id="r-001")])
        self.assertEqual([i.row for i in issues], [3])
        self.assertEqual(issues[0].code, "duplicate_receipt")

    def test_duplicate_claim(self):
        self.assertIn("duplicate_claim", codes(claim(), claim(claim_id="c-001", receipt_id="R-002")))

    def test_duplicate_claim_and_receipt(self):
        self.assertEqual(set(codes(claim(), claim())), {"duplicate_claim", "duplicate_receipt"})

    def test_currency_no_silent_conversion(self):
        self.assertIn("unsupported_currency", codes(claim(currency="EUR")))

    def test_date(self):
        self.assertIn("invalid_date", codes(claim(date="2026-02-30")))

    def test_invalid_amount(self):
        self.assertIn("invalid_amount", codes(claim(amount="hello")))

    def test_nonfinite_amount(self):
        self.assertIn("invalid_amount", codes(claim(amount="NaN")))

    def test_nonpositive(self):
        self.assertIn("nonpositive_amount", codes(claim(amount="0.00")))

    def test_fractional_cent(self):
        self.assertIn("fractional_cent", codes(claim(amount="3.001")))

    def test_whitespace(self):
        self.assertEqual(codes(claim(amount=" 20.00 ", claim_id=" C-001 ")), [])

    def test_file_and_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            inp, out = Path(temp) / "input.csv", Path(temp) / "reports" / "issues.csv"
            with inp.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow(claim(amount="36.00"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(inp), str(out)]), 1)
            with out.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["code"], "exceeds_policy_limit")

    def test_clean_file(self):
        with tempfile.TemporaryDirectory() as temp:
            inp, out = Path(temp) / "claims.csv", Path(temp) / "result.csv"
            with inp.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow(claim())
            self.assertEqual(audit_file(inp, out), [])
            self.assertEqual(len(out.read_text().splitlines()), 1)

    def test_missing_header_is_error(self):
        with tempfile.TemporaryDirectory() as temp:
            inp, out = Path(temp) / "claims.csv", Path(temp) / "result.csv"
            inp.write_text("claim_id,amount\nC-001,20\n")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(inp), str(out)]), 2)
            self.assertFalse(out.exists())

    def test_no_overwrite_source(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "claims.csv"
            path.write_text(",".join(FIELDS) + "\n")
            with self.assertRaises(ValueError):
                audit_file(path, path)


if __name__ == "__main__":
    unittest.main()
