import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from etl import main, run_etl

ROOT = Path(__file__).resolve().parents[1]


class EtlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'orders.db'
        self.report = Path(self.tmp.name) / 'report.json'
        self.source = ROOT / 'examples/orders.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_report_and_database_match_example(self):
        result = run_etl(self.source, self.db, self.report)
        expected = json.loads((ROOT / 'examples/expected-report.json').read_text(encoding='utf-8'))
        self.assertEqual(result, expected)
        self.assertEqual(json.loads(self.report.read_text(encoding='utf-8')), expected)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 4)

    def test_second_run_does_not_duplicate_records(self):
        first = run_etl(self.source, self.db, self.report)
        self.assertEqual(run_etl(self.source, self.db, self.report), first)

    def test_upsert_changes_amount_not_row_count(self):
        run_etl(self.source, self.db, self.report)
        path = Path(self.tmp.name) / 'change.json'
        path.write_text(json.dumps({'orders': [
            {'order_id': 'O-101', 'customer': 'Alpha LLC', 'amount_usd': '200.00',
             'status': 'paid', 'order_date': '2026-09-01'}]}), encoding='utf-8')
        result = run_etl(path, self.db, self.report)
        self.assertEqual((result['database_rows'], result['paid_total_usd']), (4, '290.25'))

    def test_cli_creates_both_files(self):
        code = main([str(self.source), '--database', str(self.db), '--report', str(self.report)])
        self.assertEqual(code, 0)
        self.assertTrue(self.db.is_file() and self.report.is_file())
