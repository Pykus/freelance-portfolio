"""Unit and end-to-end tests for a synthetic HTML snapshot monitor."""

import contextlib
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitor import SnapshotError, main, parse_catalog, run_snapshot

ROOT = Path(__file__).resolve().parents[1]


def item(item_id: str = "A-1", title: str = "Widget", price: str = "$2.05") -> str:
    return f'<article data-item-id="{item_id}"><h2>{title}</h2><span class="price">{price}</span></article>'


class ParsingTests(unittest.TestCase):
    def test_extracts_money_as_exact_integer_cents(self):
        self.assertEqual(parse_catalog(item())["A-1"]["price_cents"], 205)

    def test_normalizes_whitespace_and_html_entities(self):
        data = parse_catalog(item(title=" Tea &amp;  Biscuits ", price="USD 12.50"))
        self.assertEqual(data["A-1"]["title"], "Tea & Biscuits")
        self.assertEqual(data["A-1"]["price_cents"], 1250)

    def test_missing_data_and_invalid_money(self):
        for html in ("<p>No items</p>", item(title=""), item(price="$2.5"),
                     item(price="EUR 2.05"), item(price="$9999999999.99")):
            with self.subTest(html=html), self.assertRaises(SnapshotError):
                parse_catalog(html)

    def test_rejects_duplicates(self):
        with self.assertRaisesRegex(SnapshotError, "Duplicate"):
            parse_catalog(item() + item())

    def test_rejects_nested_articles(self):
        with self.assertRaisesRegex(SnapshotError, "Nested"):
            parse_catalog('<article data-item-id="A-1">' + item() + "</article>")

    def test_string_identifiers_preserve_leading_zeroes(self):
        self.assertIn("001", parse_catalog(item(item_id="001")))

    def test_zero_is_valid_and_rejected_negative(self):
        self.assertEqual(parse_catalog(item(price="$0.00"))["A-1"]["price_cents"], 0)
        with self.assertRaises(SnapshotError):
            parse_catalog(item(price="-$1.00"))


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "history.sqlite3"
        self.day1 = (ROOT / "examples/day-01.html").read_text(encoding="utf-8")
        self.day2 = (ROOT / "examples/day-02.html").read_text(encoding="utf-8")

    def test_first_snapshot_records_added(self):
        report = run_snapshot(self.db, "demo", "day-01", self.day1)
        self.assertEqual(report["counts"], {"added": 3, "updated": 0, "removed": 0, "unchanged": 0})
        self.assertEqual(report["current_count"], 3)

    def test_second_snapshot_reports_changes_and_sorted_entries(self):
        run_snapshot(self.db, "demo", "day-01", self.day1)
        report = run_snapshot(self.db, "demo", "day-02", self.day2)
        self.assertEqual(report["counts"], {"added": 1, "updated": 1, "removed": 1, "unchanged": 1})
        self.assertEqual([(c["item_id"], c["status"]) for c in report["changes"]],
                         [("A-100", "unchanged"), ("B-200", "updated"),
                          ("C-300", "added"), ("D-400", "removed")])
        self.assertEqual(report["changes"][1]["before"]["price_cents"], 700)
        self.assertEqual(report["changes"][1]["after"]["price_cents"], 650)

    def test_same_snapshot_is_idempotent(self):
        run_snapshot(self.db, "demo", "day-01", self.day1)
        replay = run_snapshot(self.db, "demo", "day-01", self.day1)
        self.assertTrue(replay["already_recorded"])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0], 3)

    def test_name_collision_never_overwrites_history(self):
        run_snapshot(self.db, "demo", "day-01", self.day1)
        with self.assertRaisesRegex(SnapshotError, "different"):
            run_snapshot(self.db, "demo", "day-01", self.day2)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)

    def test_source_histories_are_isolated(self):
        run_snapshot(self.db, "demo", "day-01", self.day1)
        report = run_snapshot(self.db, "other", "day-02", self.day2)
        self.assertEqual(report["counts"]["added"], 3)
        self.assertEqual(report["counts"]["removed"], 0)

    def test_failed_validation_preserves_history(self):
        run_snapshot(self.db, "demo", "day-01", self.day1)
        with self.assertRaises(SnapshotError):
            run_snapshot(self.db, "demo", "day-02", item(price="oops"))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)

    def test_replayed_old_snapshot_compares_to_its_own_predecessor(self):
        run_snapshot(self.db, "demo", "day-01", self.day1)
        run_snapshot(self.db, "demo", "day-02", self.day2)
        replay = run_snapshot(self.db, "demo", "day-01", self.day1)
        self.assertTrue(replay["already_recorded"])
        self.assertEqual(replay["counts"]["added"], 3)
        self.assertEqual(replay["counts"]["removed"], 0)

    def test_cli_generates_machine_readable_output(self):
        report = Path(self.tmp.name) / "out" / "report.json"
        argv = ["--html", str(ROOT / "examples/day-01.html"),
                "--database", str(self.db), "--source", "demo",
                "--snapshot", "day-01", "--output", str(report)]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(argv), 0)
        self.assertIn('"added": 3', out.getvalue())
        self.assertEqual(__import__("json").loads(report.read_text())["current_count"], 3)

    def test_cli_invalid_input_does_not_write_report(self):
        report = Path(self.tmp.name) / "report.json"
        argv = ["--html", str(ROOT / "examples/day-01.html"),
                "--database", str(self.db), "--source", "bad source",
                "--snapshot", "day-01", "--output", str(report)]
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(argv), 2)
        self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
