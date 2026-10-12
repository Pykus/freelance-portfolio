import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from etl import DataError, normalize, run_etl


class ValidationTests(unittest.TestCase):
    def test_invalid_money_rejected(self):
        for value in ('0', '-1.00', 'oops', '1.001', 'NaN', 10):
            row = {'order_id': 'O-201', 'customer': 'Valid', 'amount_usd': value,
                   'status': 'paid', 'order_date': '2026-09-01'}
            with self.subTest(value=value), self.assertRaises(DataError):
                normalize(row)

    def test_invalid_date_rejected(self):
        row = {'order_id': 'O-201', 'customer': 'Valid', 'amount_usd': '3.50',
               'status': 'paid', 'order_date': '2026-02-30'}
        with self.assertRaisesRegex(DataError, 'order_date'):
            normalize(row)

    def test_invalid_document_creates_no_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.json'
            path.write_text('{"orders":"invalid"}', encoding='utf-8')
            db = Path(tmp) / 'out.db'
            with self.assertRaises(DataError):
                run_etl(path, db, Path(tmp) / 'report.json')
            self.assertFalse(db.exists())

    def test_customer_quotes_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'orders.json'
            source.write_text(json.dumps({'orders': [
                {'order_id': 'O-201', 'customer': "O'Brien Shop", 'amount_usd': '5.00',
                 'status': 'paid', 'order_date': '2026-09-01'}]}), encoding='utf-8')
            db = Path(tmp) / 'orders.db'
            run_etl(source, db, Path(tmp) / 'report.json')
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute('SELECT customer FROM orders').fetchone()[0], "O'Brien Shop")
