import json
import tempfile
import unittest
from pathlib import Path
from validate import validate

class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.csv = Path(self.tmp.name) / "data.csv"
        self.schema = Path(self.tmp.name) / "schema.json"
        self.schema.write_text(json.dumps({"fields": {"id": "integer", "price": "decimal"}}))
    def tearDown(self):
        self.tmp.cleanup()
    def test_valid(self):
        self.csv.write_text("id,price\n1,10.50\n2,-2.00\n")
        self.assertEqual(validate(self.csv, self.schema), {"rows": 2, "errors": [], "valid": True})
    def test_bad_integer(self):
        self.csv.write_text("id,price\nabc,10.50\n")
        self.assertFalse(validate(self.csv, self.schema)["valid"])
    def test_missing_column(self):
        self.csv.write_text("id\n1\n")
        self.assertIn("missing column: price", validate(self.csv, self.schema)["errors"])
if __name__ == "__main__":
    unittest.main()
