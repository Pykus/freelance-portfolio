import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path

from audit import FIELDS, audit_rows, audit_file, main, required_role

AS_OF = date(2026, 10, 24)


def request(**changes):
    row = {
        "request_id": "PR-001", "submitted_date": "2026-10-20",
        "amount_usd": "300.00", "status": "approved", "approver_role": "staff",
    }
    row.update(changes)
    return row


def codes(*rows):
    return [issue.code for issue in audit_rows(rows, AS_OF)]


class ApprovalTests(unittest.TestCase):
    def test_valid_small(self):
        self.assertEqual(codes(request()), [])

    def test_roles_at_boundaries(self):
        self.assertEqual(required_role(Decimal("500")), 1)
        self.assertEqual(required_role(Decimal("500.01")), 2)
        self.assertEqual(required_role(Decimal("5000")), 2)
        self.assertEqual(required_role(Decimal("5000.01")), 3)

    def test_large_requires_director(self):
        self.assertIn("insufficient_approval", codes(request(
            amount_usd="6000", approver_role="manager")))

    def test_manager_approval(self):
        self.assertEqual(codes(request(amount_usd="501", approver_role="manager")), [])

    def test_director_approval(self):
        self.assertEqual(codes(request(amount_usd="6000", approver_role="director")), [])

    def test_pending_no_approval_needed(self):
        self.assertEqual(codes(request(status="pending", approver_role="none")), [])

    def test_pending_overdue(self):
        self.assertIn("pending_over_14_days", codes(request(
            status="pending", approver_role="none", submitted_date="2026-10-01")))

    def test_pending_exact_boundary(self):
        self.assertNotIn("pending_over_14_days", codes(request(
            status="pending", approver_role="none", submitted_date="2026-10-10")))

    def test_duplicate_id(self):
        self.assertIn("duplicate_request_id", codes(request(), request(request_id="pr-001")))

    def test_missing_id(self):
        self.assertIn("missing_field", codes(request(request_id="")))

    def test_future(self):
        self.assertIn("future_submission", codes(request(submitted_date="2026-10-25")))

    def test_date_invalid(self):
        self.assertIn("invalid_date", codes(request(submitted_date="invalid")))

    def test_amount_invalid(self):
        self.assertIn("invalid_amount", codes(request(amount_usd="bad")))

    def test_amount_nan(self):
        self.assertIn("invalid_amount", codes(request(amount_usd="NaN")))

    def test_amount_negative(self):
        self.assertIn("invalid_amount", codes(request(amount_usd="-1")))

    def test_fractional_cent(self):
        self.assertIn("invalid_amount", codes(request(amount_usd="3.001")))

    def test_bad_status(self):
        self.assertIn("invalid_status", codes(request(status="waiting")))

    def test_bad_role(self):
        self.assertIn("invalid_approver_role", codes(request(approver_role="intern")))

    def test_rejected_without_role(self):
        self.assertEqual(codes(request(status="rejected", approver_role="none")), [])

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp, out = root/"requests.csv", root/"issues.csv"
            with inp.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow(request(amount_usd="800"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(inp), str(out), "--as-of", "2026-10-24"]), 1)
            with out.open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_no_source_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            inp = Path(directory) / "input.csv"
            inp.write_text(",".join(FIELDS) + "\n")
            with self.assertRaises(ValueError):
                audit_file(inp, inp, AS_OF)

    def test_invalid_date_cli(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["none.csv", "out.csv", "--as-of", "oops"]), 2)


if __name__ == "__main__":
    unittest.main()
