import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
from pathlib import Path

from audit import FIELDS, audit_rows, audit_file, main

DAY = date(2026, 10, 23)


def shipment(**kwargs):
    row = {"shipment_id": "S-001", "dispatched_date": "2026-10-20",
           "eta_date": "2026-10-24", "delivered_date": "",
           "status": "in_transit"}
    row.update(kwargs)
    return row


def codes(*rows):
    return [i.code for i in audit_rows(rows, DAY)]


class ShipmentTests(unittest.TestCase):
    def test_on_time_transit(self):
        self.assertEqual(codes(shipment()), [])

    def test_overdue(self):
        self.assertIn("overdue_in_transit", codes(shipment(eta_date="2026-10-22")))

    def test_exact_eta_not_overdue(self):
        self.assertNotIn("overdue_in_transit", codes(shipment(eta_date="2026-10-23")))

    def test_late_delivery(self):
        self.assertIn("delivered_late", codes(shipment(
            status="delivered", delivered_date="2026-10-25")))

    def test_on_time_delivery(self):
        self.assertEqual(codes(shipment(
            status="delivered", delivered_date="2026-10-23")), [])

    def test_no_delivery_date(self):
        self.assertIn("missing_delivery_date", codes(shipment(status="delivered")))

    def test_eta_before_dispatch(self):
        self.assertIn("eta_before_dispatch", codes(shipment(eta_date="2026-10-18")))

    def test_delivery_before_dispatch(self):
        self.assertIn("delivery_before_dispatch", codes(shipment(
            status="delivered", delivered_date="2026-10-19")))

    def test_future_dispatch(self):
        self.assertIn("future_dispatch", codes(shipment(dispatched_date="2026-10-25")))

    def test_unexpected_delivery_date(self):
        self.assertIn("unexpected_delivery_date", codes(shipment(
            status="in_transit", delivered_date="2026-10-21")))

    def test_cancelled_with_no_delivery(self):
        self.assertEqual(codes(shipment(status="cancelled")), [])

    def test_cancelled_with_delivery(self):
        self.assertIn("unexpected_delivery_date", codes(shipment(
            status="cancelled", delivered_date="2026-10-23")))

    def test_unknown_status(self):
        self.assertIn("invalid_status", codes(shipment(status="lost")))

    def test_bad_date(self):
        self.assertIn("invalid_date", codes(shipment(eta_date="invalid")))

    def test_duplicate_casefold(self):
        self.assertIn("duplicate_shipment", codes(
            shipment(), shipment(shipment_id="s-001")))

    def test_missing_field(self):
        self.assertIn("missing_field", codes(shipment(shipment_id="")))

    def test_blank_delivery_valid(self):
        self.assertEqual(codes(shipment()), [])

    def test_empty_csv_data(self):
        self.assertEqual(audit_rows([], DAY), [])

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp, out = root/"in.csv", root/"out.csv"
            with inp.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow(shipment(eta_date="2026-10-22"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(inp), str(out), "--as-of", "2026-10-23"]), 1)
            with out.open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 1)

    def test_schema_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp = root/"in.csv"
            inp.write_text("shipment_id\nS-001\n")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(inp), str(root/"out.csv"),
                                       "--as-of", "2026-10-23"]), 2)

    def test_no_source_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"input.csv"
            path.write_text(",".join(FIELDS)+"\n")
            with self.assertRaises(ValueError):
                audit_file(path, path, DAY)

    def test_invalid_as_of(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["x.csv", "out.csv", "--as-of", "invalid"]), 2)


if __name__ == "__main__":
    unittest.main()
