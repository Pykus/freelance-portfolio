"""Tests for the manually usable search-plan and lead-list workflow."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from footprint_batch import (
    build_query, consolidate, consolidate_hits, fixture_hits, load_fixture, main,
    normalize_url, plan_queries, planned_rows, read_footprints, read_locations,
    read_results_csv, safe_csv_cell, write_plan, write_report,
)

ROOT = Path(__file__).resolve().parents[1]


class WebsiteResearchTests(unittest.TestCase):
    def setUp(self):
        self.locations = read_locations(ROOT / "examples/locations.csv")
        self.footprints = read_footprints(ROOT / "examples/footprints.txt")
        self.fixture = load_fixture(ROOT / "examples/mock-results.json")

    def test_query_plan_uses_town_area_and_postcode_for_each_footprint(self):
        self.assertEqual(len(plan_queries(self.locations, self.footprints)), 8)
        self.assertIn(("Shrewsbury", self.footprints[0], "01743"),
                      plan_queries(self.locations, self.footprints))

    def test_query_is_ready_to_copy_into_publicwww(self):
        self.assertEqual(
            build_query("Website by Northstar Web Studio", "SY1"),
            'depth:all site:uk "Website by Northstar Web Studio" "SY1"')

    def test_query_escapes_embedded_quotes(self):
        self.assertEqual(build_query('Website by "Northstar"', "SY1"),
                         'depth:all site:uk "Website by \\"Northstar\\"" "SY1"')

    def test_query_plan_removes_repeated_location_terms(self):
        locs = [{"town": "Town", "area_code": "Town", "postcodes": "SY1|SY1"}]
        self.assertEqual(len(plan_queries(locs, ["signature"])), 2)

    def test_different_footprints_are_distinct_queries(self):
        self.assertEqual(len(plan_queries(self.locations, self.footprints)), 8)
        self.assertNotEqual(planned_rows(self.locations, self.footprints)[0]["query"],
                            planned_rows(self.locations, self.footprints)[4]["query"])

    def test_normalizes_www_scheme_and_ignores_tracking(self):
        self.assertEqual(normalize_url("HTTP://WWW.Example.COM/shop/?x=1#top"),
                         "https://example.com/shop")

    def test_rejects_unsafe_url_schemes(self):
        for value in ("ftp://example.com", "file:///etc/passwd",
                      "javascript:alert(1)", "not-a-url"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_url(value)

    def test_rejects_userinfo_ports_and_invalid_hosts(self):
        for value in ("https://a:password@example.com",
                      "https://example.com:8080",
                      "https://example.com:invalid",
                      "https://hello world.example", "https://localhost"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_url(value)

    def test_fixture_counts_explain_the_business_example(self):
        rows, summary = consolidate(self.locations, self.footprints, self.fixture)
        self.assertEqual(summary, {
            "queries": 8, "hits": 7, "unique_sites": 3,
            "duplicate_hits": 3, "invalid_urls": 1,
        })
        self.assertEqual([r["domain"] for r in rows],
                         ["cobalt-dental.example", "flower-shop.example",
                          "riverbank-bakery.example"])

    def test_same_domain_across_paths_and_footprints_stays_one_lead(self):
        rows, _ = consolidate(self.locations, self.footprints, self.fixture)
        bakery = next(r for r in rows if r["domain"] == "riverbank-bakery.example")
        self.assertEqual(bakery["hit_count"], 3)
        self.assertEqual(bakery["matched_terms"], "01743 | Shrewsbury")
        self.assertEqual(
            bakery["matched_footprints"],
            "Powered by Northstar Site Engine | Website by Northstar Web Studio")
        self.assertEqual(len(bakery["search_queries"].split(" | ")), 3)

    def test_preserves_separate_subdomains(self):
        q = planned_rows(self.locations, self.footprints)[0]["query"]
        rows, summary = consolidate_hits(self.locations, self.footprints, [
            {"query": q, "url": "https://shop.example.com/", "title": "shop"},
            {"query": q, "url": "https://example.com/", "title": "main"},
        ])
        self.assertEqual(summary["unique_sites"], 2)
        self.assertEqual(len(rows), 2)

    def test_csv_import_equivalent_to_json_example(self):
        imported = read_results_csv(ROOT / "examples/manual-search-results.csv")
        actual_rows, actual_summary = consolidate_hits(
            self.locations, self.footprints, imported)
        expected_rows, expected_summary = consolidate(
            self.locations, self.footprints, self.fixture)
        self.assertEqual(actual_summary, expected_summary)
        self.assertEqual(actual_rows, expected_rows)

    def test_unknown_query_is_not_silently_attributed_to_another_town(self):
        with self.assertRaisesRegex(ValueError, "Unknown search query"):
            consolidate_hits(self.locations, self.footprints, [
                {"query": "some unrelated query",
                 "url": "https://example.com", "title": "Wrong"}
            ])

    def test_zero_hits_still_reports_planned_work(self):
        rows, summary = consolidate(self.locations, self.footprints, {})
        self.assertEqual(rows, [])
        self.assertEqual(summary["queries"], 8)
        self.assertEqual(summary["unique_sites"], 0)

    def test_csv_formula_cells_are_neutralized(self):
        for value in ("=2+2", "+SUM(1)", "-1+3", "@SUM(1)", " =HYPERLINK(1)"):
            self.assertTrue(safe_csv_cell(value).startswith("'"))
        self.assertEqual(safe_csv_cell("Riverbank Bakery"), "Riverbank Bakery")

    def test_plan_only_is_usable_before_searching(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "plan"
            self.assertEqual(main(["--plan-only", "--output", str(target)]), 0)
            self.assertTrue((target / "queries.csv").is_file())
            self.assertFalse((target / "sites.csv").exists())
            with (target / "queries.csv").open(newline="") as inp:
                rows = list(csv.DictReader(inp))
            self.assertEqual(len(rows), 8)
            self.assertIn("depth:all site:uk", rows[0]["query"])

    def test_run_demo_exports_human_readable_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["--demo", "--output", tmp]), 0)
            with (Path(tmp) / "sites.csv").open(newline="") as inp:
                rows = list(csv.DictReader(inp))
            self.assertEqual(len(rows), 3)
            self.assertIn("matched_footprints", rows[0])
            self.assertIn("search_queries", rows[0])
            self.assertEqual(
                json.loads((Path(tmp) / "summary.json").read_text())["hits"], 7)

    def test_run_imported_csv_exports_same_sites(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = main([
                "--results-csv",
                str(ROOT / "examples/manual-search-results.csv"),
                "--output", tmp,
            ])
            self.assertEqual(result, 0)
            with (Path(tmp) / "sites.csv").open(newline="") as inp:
                self.assertEqual(len(list(csv.DictReader(inp))), 3)

    def test_csv_input_rejects_missing_query_and_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            path.write_text("query,title\nabc,example\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires query,url"):
                read_results_csv(path)
            path.write_text("query,url,title\n,https://example.com,x\n",
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                read_results_csv(path)

    def test_rejects_missing_location_columns_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.csv"
            path.write_text("town,area_code\nShrewsbury,01743\n")
            with self.assertRaises(ValueError):
                read_locations(path)
            path.write_text("town,area_code,postcodes\nShrewsbury,,SY1\n")
            with self.assertRaises(ValueError):
                read_locations(path)

    def test_footprint_comment_and_duplicate_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "footprints.txt"
            path.write_text("# note\nFirst\nFirst\nSecond\n")
            self.assertEqual(read_footprints(path), ["First", "Second"])
            path.write_text("# note\n")
            with self.assertRaises(ValueError):
                read_footprints(path)

    def test_rejects_invalid_fixture_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.json"
            path.write_text('{"query": [{"url": 1, "title": "bad"}]}')
            with self.assertRaises(ValueError):
                load_fixture(path)

    def test_write_report_escapes_formula_title(self):
        rows, counts = consolidate(self.locations, self.footprints, self.fixture)
        rows[0]["title"] = "=HYPERLINK(1)"
        with tempfile.TemporaryDirectory() as tmp:
            write_report(rows, counts, Path(tmp))
            with (Path(tmp) / "sites.csv").open(newline="") as inp:
                saved = list(csv.DictReader(inp))
            self.assertEqual(saved[0]["title"], "'=HYPERLINK(1)")


if __name__ == "__main__":
    unittest.main()
