"""Regression and edge-case tests for the offline search workflow."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from footprint_batch import (consolidate, load_fixture, main, normalize_url,
                             plan_queries, read_footprints, read_locations,
                             safe_csv_cell, write_report)


class BatchSearchTests(unittest.TestCase):
    def setUp(self):
        self.location = [{"town": "Eastmere", "area_code": "01234", "postcodes": "EX1|EX2"}]
        self.footprints = ["Built by DemoWeb"]
        self.fixture = {
            "Built by DemoWeb|Eastmere": [
                {"url": "https://www.bakery.example/", "title": "Bakery"},
                {"url": "https://studio.example/catalog/?ref=1", "title": "Studio"}],
            "Built by DemoWeb|01234": [
                {"url": "http://BAKERY.example", "title": "Repeated"},
                {"url": "ftp://unsafe.example/", "title": "Unsupported"}],
        }

    def test_plan_queries_all_terms(self):
        self.assertEqual(len(plan_queries(self.location, self.footprints)), 4)

    def test_plan_deduplicates_repeated_terms(self):
        location = [{"town": "Eastmere", "area_code": "Eastmere", "postcodes": "EX1|EX1"}]
        self.assertEqual(len(plan_queries(location, self.footprints)), 2)

    def test_different_footprints_generate_distinct_queries(self):
        self.assertEqual(len(plan_queries(self.location, ["a", "b"])), 8)

    def test_url_canonicalization(self):
        self.assertEqual(normalize_url("HTTP://WWW.Example.COM/shop/?x=1#top"),
                         "https://example.com/shop")

    def test_url_refuses_untrusted_schemes(self):
        for text in ("file:///etc/passwd", "javascript:alert(1)", "not a URL"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    normalize_url(text)

    def test_url_refuses_credentials_and_ports(self):
        for text in ("https://alice:password@example.com", "https://example.com:8080"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    normalize_url(text)

    def test_consolidation_reports_duplicates_and_invalid_urls(self):
        rows, report = consolidate(self.location, self.footprints, self.fixture)
        self.assertEqual(len(rows), 2)
        self.assertEqual(report, {"queries": 4, "hits": 4, "unique_sites": 2,
                                  "duplicate_hits": 1, "invalid_urls": 1})
        self.assertEqual([row["url"] for row in rows],
                         ["https://bakery.example/", "https://studio.example/catalog"])

    def test_no_hits_produce_zero_counts(self):
        rows, counts = consolidate(self.location, self.footprints, {})
        self.assertEqual(rows, [])
        self.assertEqual(counts["queries"], 4)
        self.assertEqual(counts["hits"], 0)

    def test_csv_formula_escaping(self):
        self.assertEqual(safe_csv_cell("=SUM(1,1)"), "'=SUM(1,1)")
        self.assertEqual(safe_csv_cell("ordinary"), "ordinary")

    def test_output_files_and_csv_formula_escaping(self):
        rows, counts = consolidate(self.location, self.footprints, self.fixture)
        rows[0]["title"] = "=HYPERLINK(\"bad\")"
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            write_report(rows, counts, output)
            with (output / "sites.csv").open(newline="", encoding="utf-8") as stream:
                csv_rows = list(csv.DictReader(stream))
            self.assertEqual(len(csv_rows), 2)
            self.assertTrue(csv_rows[0]["title"].startswith("'="))
            self.assertEqual(json.loads((output / "summary.json").read_text()), counts)

    def test_location_validation_and_file_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "places.csv"
            path.write_text("town,area_code,postcodes\nEastmere,01234,EX1|EX2\n")
            self.assertEqual(read_locations(path), self.location)
            path.write_text("town,area_code\nEastmere,01234\n")
            with self.assertRaises(ValueError):
                read_locations(path)

    def test_empty_and_invalid_location_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "places.csv"
            path.write_text("town,area_code,postcodes\n")
            with self.assertRaises(ValueError):
                read_locations(path)
            path.write_text("town,area_code,postcodes\nEastmere,,EX1\n")
            with self.assertRaises(ValueError):
                read_locations(path)

    def test_footprint_comments_duplicates_and_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "footprints.txt"
            path.write_text("# comment\nDemoWeb\nDemoWeb\n\nSecond\n")
            self.assertEqual(read_footprints(path), ["DemoWeb", "Second"])
            path.write_text("# no active footprints\n")
            with self.assertRaises(ValueError):
                read_footprints(path)

    def test_fixture_schema_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.json"
            path.write_text('{"bad": [{"url": 8, "title": "Hello"}]}')
            with self.assertRaises(ValueError):
                load_fixture(path)
            path.write_text('{"ok": [{"url": "https://example.com", "title": "Hello"}]}')
            self.assertEqual(len(load_fixture(path)["ok"]), 1)

    def test_complete_cli_from_synthetic_files(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            result = main(["--locations", str(root / "examples/locations.csv"),
                           "--footprints", str(root / "examples/footprints.txt"),
                           "--fixture", str(root / "examples/mock-results.json"),
                           "--output", str(output)])
            self.assertEqual(result, 0)
            summary = json.loads((output / "summary.json").read_text())
            self.assertEqual(summary["unique_sites"], 2)
            self.assertEqual(summary["duplicate_hits"], 1)
            self.assertEqual(summary["invalid_urls"], 1)


if __name__ == "__main__":
    unittest.main()
