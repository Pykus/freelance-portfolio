"""Behavioral tests with generated fictional emails and temporary storage."""

import csv
from email.message import EmailMessage
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from order_intake import InvalidOrder, connect, ingest, parse_order


BODY = """Order-ID: SO-1001
Customer: Example Stationery
Item: PEN-BLUE, 3, 2.40
Item: PAPER-A4, 2, 5.25
"""


def email_bytes(body=BODY, message_id="<msg-1@example.test>", *,
                sender="orders@example.test", subject="Order received",
                html=False, multipart=False):
    email = EmailMessage()
    if message_id is not None:
        email["Message-ID"] = message_id
    email["From"] = sender
    email["To"] = "warehouse@example.test"
    email["Subject"] = subject
    email.set_content(body, subtype="html" if html else "plain")
    if multipart:
        email.add_alternative("<p>Rich formatting</p>", subtype="html")
    return email.as_bytes()


class OrderIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        self.db = self.root / "state" / "orders.sqlite3"
        self.report = self.root / "output" / "report.csv"

    def add(self, name, raw):
        (self.inbox / name).write_bytes(raw)

    def report_rows(self):
        with self.report.open(newline="", encoding="utf-8") as stream:
            return list(csv.DictReader(stream))

    def test_total_is_exact_and_lines_persisted(self):
        self.add("one.eml", email_bytes())
        self.assertEqual(ingest(self.inbox, self.db, self.report)["imported"], 1)
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT total_cents FROM orders").fetchone()[0], 1770)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM order_lines").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT quantity FROM order_lines ORDER BY line_no").fetchall(), [(3,), (2,)])
        self.assertEqual(self.report_rows()[0]["total"], "17.70")

    def test_duplicate_message_is_idempotent_across_runs(self):
        self.add("one.eml", email_bytes())
        ingest(self.inbox, self.db, self.report)
        self.assertEqual(ingest(self.inbox, self.db, self.report), {"imported": 0, "duplicate": 1, "rejected": 0})
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)

    def test_duplicate_order_id_with_different_message_id(self):
        self.add("a.eml", email_bytes())
        self.add("b.eml", email_bytes(message_id="<msg-2@example.test>"))
        self.assertEqual(ingest(self.inbox, self.db, self.report)["duplicate"], 1)

    def test_missing_message_id(self):
        with self.assertRaisesRegex(InvalidOrder, "Message-ID"):
            parse_order(email_bytes(message_id=None))

    def test_missing_customer(self):
        with self.assertRaisesRegex(InvalidOrder, "Customer"):
            parse_order(email_bytes(BODY.replace("Customer: Example Stationery\n", "")))

    def test_invalid_quantity_negative(self):
        with self.assertRaisesRegex(InvalidOrder, "quantity"):
            parse_order(email_bytes(BODY.replace("3, 2.40", "-3, 2.40")))

    def test_invalid_quantity_fractional(self):
        with self.assertRaisesRegex(InvalidOrder, "quantity"):
            parse_order(email_bytes(BODY.replace("3, 2.40", "1.5, 2.40")))

    def test_invalid_price(self):
        with self.assertRaisesRegex(InvalidOrder, "price"):
            parse_order(email_bytes(BODY.replace("2.40", "2.4")))

    def test_zero_price_is_supported(self):
        order = parse_order(email_bytes(BODY.replace("2.40", "0.00")))
        self.assertEqual(order.total_cents, 1050)

    def test_html_only_is_rejected(self):
        with self.assertRaisesRegex(InvalidOrder, "plain-text"):
            parse_order(email_bytes("<p>order</p>", html=True))

    def test_multipart_selects_plain_text(self):
        self.assertEqual(parse_order(email_bytes(multipart=True)).total_cents, 1770)

    def test_sender_must_be_valid(self):
        with self.assertRaisesRegex(InvalidOrder, "sender"):
            parse_order(email_bytes(sender="anonymous"))

    def test_subject_must_indicate_order(self):
        with self.assertRaisesRegex(InvalidOrder, "subject"):
            parse_order(email_bytes(subject="General inquiry"))

    def test_unknown_body_field_is_rejected(self):
        with self.assertRaisesRegex(InvalidOrder, "unknown field"):
            parse_order(email_bytes(BODY + "Admin: sudo\n"))

    def test_rejection_does_not_block_next_email(self):
        self.add("a-bad.eml", email_bytes(BODY.replace("2.40", "wrong")))
        self.add("b-good.eml", email_bytes(message_id="<msg-2@example.test>"))
        self.assertEqual(ingest(self.inbox, self.db, self.report), {"imported": 1, "duplicate": 0, "rejected": 1})
        self.assertEqual([row["status"] for row in self.report_rows()], ["rejected", "imported"])

    def test_large_email_is_rejected_without_reading_it(self):
        self.add("large.eml", b"x" * 1_000_001)
        self.assertEqual(ingest(self.inbox, self.db, self.report)["rejected"], 1)
        self.assertIn("1 MB", self.report_rows()[0]["details"])

    def test_empty_inbox_writes_header(self):
        self.assertEqual(ingest(self.inbox, self.db, self.report), {"imported": 0, "duplicate": 0, "rejected": 0})
        self.assertEqual(self.report.read_text(encoding="utf-8").strip(), "source_file,status,order_id,total,details")

    def test_error_when_directory_does_not_exist(self):
        with self.assertRaisesRegex(ValueError, "existing directory"):
            ingest(self.root / "missing", self.db, self.report)

    def test_cli_writes_machine_readable_summary(self):
        self.add("one.eml", email_bytes())
        script = Path(__file__).resolve().parents[1] / "order_intake.py"
        result = subprocess.run(
            [sys.executable, str(script), "--input", str(self.inbox),
             "--db", str(self.db), "--report", str(self.report)],
            capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"imported": 1, "duplicate": 0, "rejected": 0})


if __name__ == "__main__":
    unittest.main()
