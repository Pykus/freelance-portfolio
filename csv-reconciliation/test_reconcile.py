import tempfile
import unittest
from pathlib import Path
from reconcile import compare, read

class Tests(unittest.TestCase):
    def test_diff(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.csv", Path(d) / "b.csv"
            a.write_text("id,amount\n001,1.00\n002,2.00\n004,4.00\n")
            b.write_text("id,amount\n001,1.00\n002,3.00\n003,3.00\n")
            self.assertEqual(compare(a, b), {"added": ["003"], "removed": ["004"], "changed": ["002"], "unchanged": 1})
    def test_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.csv"
            p.write_text("id,amount\n01,1\n01,2\n")
            with self.assertRaises(ValueError): read(p)
    def test_precision(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.csv"
            p.write_text("id,amount\n01,1.234\n")
            with self.assertRaises(ValueError): read(p)
if __name__ == "__main__":
    unittest.main()
