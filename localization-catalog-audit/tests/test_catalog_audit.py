"""Regression tests for translation catalog quality checks."""
import csv
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from catalog_audit import (
    audit, export, main, placeholders, read_catalog, safe_spreadsheet
)

ROOT = Path(__file__).resolve().parents[1]


class CatalogAuditTests(unittest.TestCase):
    def setUp(self):
        self.base = read_catalog(ROOT / "examples/english.csv")
        self.es = read_catalog(ROOT / "examples/spanish.csv")

    def test_example_has_five_specific_issues(self):
        issues, summary = audit(self.base, self.es, "es")
        self.assertEqual(summary["source_keys"], 6)
        self.assertEqual(summary["target_keys"], 6)
        self.assertEqual(summary["issue_count"], 5)
        self.assertEqual(summary["issues_by_code"], {
            "empty_translation": 1,
            "invalid_format": 1,
            "missing_key": 1,
            "placeholder_mismatch": 1,
            "unexpected_key": 1,
        })
        self.assertEqual(len(issues), 5)

    def test_correct_translation_has_zero_issues(self):
        issues, summary = audit(self.base, self.base, "pl-PL")
        self.assertEqual(issues, [])
        self.assertEqual(summary["issue_count"], 0)

    def test_missing_keys_reported(self):
        issues, _ = audit({"name": "Hi"}, {}, "es")
        self.assertEqual(issues[0]["issue"], "missing_key")

    def test_unexpected_keys_reported(self):
        issues, _ = audit({}, {"other": "Hola"}, "es")
        self.assertEqual(issues[0]["issue"], "unexpected_key")

    def test_empty_translations(self):
        issues, _ = audit({"name": "Hi"}, {"name": "   "}, "es")
        self.assertEqual(issues[0]["issue"], "empty_translation")

    def test_missing_placeholder_is_detected(self):
        issues, _ = audit({"a": "Hello {user}"},
                          {"a": "Hola"}, "es")
        self.assertEqual(issues[0]["issue"], "placeholder_mismatch")

    def test_wrong_placeholder_is_detected(self):
        issues, _ = audit({"a": "Hello {user}"},
                          {"a": "Hola {name}"}, "es")
        self.assertIn("user", issues[0]["details"])
        self.assertIn("name", issues[0]["details"])

    def test_repeated_placeholder_counts_matter(self):
        issues, _ = audit({"a": "{name}, {name}!"},
                          {"a": "{name}!"}, "es")
        self.assertEqual(issues[0]["issue"], "placeholder_mismatch")

    def test_escaped_curly_braces_are_not_placeholders(self):
        self.assertEqual(placeholders("{{tag}} + {name}"),
                         Counter({"name": 1}))

    def test_malformed_target_is_an_issue_not_a_crash(self):
        issues, _ = audit({"a": "{name}"}, {"a": "{name"}, "es")
        self.assertEqual(issues[0]["issue"], "invalid_format")

    def test_invalid_base_format_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Base catalog"):
            audit({"a": "{name"}, {"a": "Hola"}, "es")

    def test_rejects_attribute_and_index_placeholders(self):
        for value in ("{user.name}", "{user[0]}", "{user!r}", "{user:>10}"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                placeholders(value)

    def test_invalid_locale_rejected(self):
        with self.assertRaises(ValueError):
            audit(self.base, self.es, "not_a_locale")

    def test_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "labels.csv"
            file.write_text("key,text\nwelcome,Hi\nwelcome,Hola\n")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                read_catalog(file)

    def test_invalid_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "labels.csv"
            file.write_text("key,text\nbad key,Hi\n")
            with self.assertRaisesRegex(ValueError, "invalid key"):
                read_catalog(file)

    def test_missing_headers_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "labels.csv"
            file.write_text("id,message\n1,Hello\n")
            with self.assertRaisesRegex(ValueError, "requires"):
                read_catalog(file)

    def test_malformed_csv_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "labels.csv"
            file.write_text("key,text\nwelcome,Hi,unexpected\n")
            with self.assertRaisesRegex(ValueError, "malformed"):
                read_catalog(file)

    def test_utf8_bom_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "labels.csv"
            file.write_text("\ufeffkey,text\nwelcome,Héllo\n", encoding="utf-8")
            self.assertEqual(read_catalog(file)["welcome"], "Héllo")

    def test_spreadsheet_formula_protection(self):
        self.assertEqual(safe_spreadsheet("=1+1"), "'=1+1")
        self.assertEqual(safe_spreadsheet(" +A1"), "' +A1")
        self.assertEqual(safe_spreadsheet("Hola"), "Hola")

    def test_report_export_contains_all_codes(self):
        issues, summary = audit(self.base, self.es, "es")
        with tempfile.TemporaryDirectory() as tmp:
            export(issues, summary, Path(tmp))
            with (Path(tmp) / "issues.csv").open(newline="", encoding="utf-8") as f:
                saved = list(csv.DictReader(f))
            self.assertEqual(len(saved), 5)
            self.assertEqual(json.loads(
                (Path(tmp) / "summary.json").read_text())["issue_count"], 5)

    def test_deterministic_output(self):
        first = audit(self.base, self.es, "es")
        second = audit(dict(reversed(list(self.base.items()))),
                       dict(reversed(list(self.es.items()))), "es")
        self.assertEqual(first, second)

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main([
                "--source", str(ROOT / "examples/english.csv"),
                "--target", str(ROOT / "examples/spanish.csv"),
                "--locale", "es", "--output", tmp]), 0)
            self.assertTrue((Path(tmp) / "issues.csv").is_file())
            self.assertTrue((Path(tmp) / "summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
