"""Tests for deterministic website migration redirect audits."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from redirect_audit import audit, follow, main, normalize_url, read_csv, run, safe_cell

BASE = Path(__file__).resolve().parents[1]


class RedirectAuditTests(unittest.TestCase):
    def setUp(self):
        self.old = read_csv(BASE / "examples/old-urls.csv", ("old_url",))
        self.map = read_csv(BASE / "examples/redirects.csv", ("source", "target"))

    def test_normalization_keeps_important_url_parts(self):
        self.assertEqual(normalize_url(" HTTPS://OLD.Example/a?x=1#here "),
                         "https://old.example/a?x=1")
        self.assertNotEqual(normalize_url("http://old.example/a"),
                            normalize_url("https://old.example/a"))
        self.assertNotEqual(normalize_url("https://old.example/a"),
                            normalize_url("https://old.example/a/"))

    def test_unsupported_urls(self):
        for value in ("ftp://old.example/a", "/relative", "not a URL",
                      "https://old.example:9000/a", "https://old..example/a"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_url(value)

    def test_direct_one_hop(self):
        rows, _, _ = audit(self.old, self.map)
        self.assertEqual(rows[0]["status"], "direct")
        self.assertEqual(rows[0]["final_url"], "https://new.example/about")
        self.assertEqual(rows[0]["hops"], "1")

    def test_sample_summary(self):
        rows, findings, stats = audit(self.old, self.map)
        self.assertEqual(stats, {"inventory_urls": 6, "redirect_rules": 8,
                                 "direct": 2, "chained": 1, "loops": 2,
                                 "missing": 1, "findings": 5})
        self.assertEqual(len(rows), 6)
        self.assertEqual(len(findings), 5)

    def test_chain(self):
        rows, _, _ = audit(self.old, self.map)
        pricing = next(r for r in rows if r["old_url"].endswith("/pricing"))
        self.assertEqual((pricing["status"], pricing["hops"],
                          pricing["final_url"]),
                         ("chained", "2", "https://new.example/plans"))

    def test_cycles(self):
        self.assertEqual(follow("a", {"a": "b", "b": "a"}), ("loop", "", 2))
        self.assertEqual(follow("a", {"a": "a"}), ("loop", "", 1))
        self.assertEqual(follow("a", {"a": "b", "b": "c", "c": "b"}),
                         ("loop", "", 3))

    def test_missing(self):
        self.assertEqual(follow("a", {}), ("missing", "", 0))

    def test_duplicate_source_keeps_first(self):
        old = [{"old_url": "https://old.example/a"}]
        maps = [{"source": "https://old.example/a", "target": "https://new.example/a"},
                {"source": "https://old.example/a", "target": "https://new.example/b"}]
        rows, findings, stats = audit(old, maps)
        self.assertEqual(rows[0]["final_url"], "https://new.example/a")
        self.assertEqual(stats["redirect_rules"], 1)
        self.assertTrue(any(f["code"] == "duplicate_redirect_source" for f in findings))

    def test_intermediate_step_not_reported_as_extra(self):
        _, findings, _ = audit(self.old, self.map)
        extras = [f["source"] for f in findings if f["code"] == "unlisted_source"]
        self.assertEqual(extras, ["https://old.example/obsolete"])

    def test_invalid_inventory_mapping(self):
        rows, findings, stats = audit(
            [{"old_url": "bad"}, {"old_url": "https://old.example/a"}],
            [{"source": "bad", "target": "https://new.example/a"}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats["redirect_rules"], 0)
        self.assertEqual({f["code"] for f in findings},
                         {"invalid_inventory_url", "invalid_redirect_url", "missing_redirect"})

    def test_duplicate_inventory_only_counted_once(self):
        inventory = [{"old_url": "https://old.example/a"}] * 2
        rows, findings, stats = audit(inventory, [])
        self.assertEqual(stats["inventory_urls"], 1)
        self.assertEqual(len(rows), 1)
        self.assertTrue(any(f["code"] == "duplicate_inventory_url" for f in findings))

    def test_spreadsheet_safety(self):
        self.assertEqual(safe_cell("=2+3"), "'=2+3")
        self.assertEqual(safe_cell(" @SUM(1)"), "' @SUM(1)")
        self.assertEqual(safe_cell("normal"), "normal")

    def test_end_to_end_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats, blocked = run(BASE / "examples/old-urls.csv",
                                 BASE / "examples/redirects.csv", Path(tmp))
            self.assertTrue(blocked)
            self.assertEqual(stats["findings"], 5)
            with (Path(tmp) / "audit.csv").open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 6)
            with (Path(tmp) / "findings.csv").open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 5)
            self.assertEqual(json.loads((Path(tmp) / "summary.json").read_text()), stats)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["--output", tmp]), 0)
            self.assertEqual(main(["--output", tmp, "--fail-on-errors"]), 1)

    def test_clean_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "old.csv", Path(tmp) / "rules.csv"
            a.write_text("old_url\nhttps://old.example/a\n")
            b.write_text("source,target\nhttps://old.example/a,https://new.example/a\n")
            self.assertEqual(main(["--inventory", str(a), "--redirects", str(b),
                                   "--output", tmp, "--fail-on-errors"]), 0)

    def test_bad_input_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "data.csv"
            p.write_text("wrong\na\n")
            with self.assertRaises(ValueError):
                read_csv(p, ("old_url",))
            p.write_text("old_url\n")
            with self.assertRaises(ValueError):
                read_csv(p, ("old_url",))


if __name__ == "__main__":
    unittest.main()
