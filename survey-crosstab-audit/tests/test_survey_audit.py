"""Behavior and regression tests for the survey quality audit."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from survey_audit import CodebookError, audit, export, read_codebook  # noqa: E402

EXAMPLES = ROOT / "examples"


class SurveyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.book = read_codebook(EXAMPLES / "codebook.json")

    def run_rows(self, rows):
        path = self.work / "responses.csv"
        path.write_text("response_id,region,service_score,recommend\n" + rows,
                        encoding="utf-8")
        return audit(path, self.book)

    def test_example_counts(self):
        result = audit(EXAMPLES / "responses.csv", self.book)
        self.assertEqual((result["rows_read"], result["included_respondents"],
                          result["excluded_rows"]), (9, 7, 2))

    def test_example_issue_types(self):
        codes = [item["code"] for item in audit(EXAMPLES / "responses.csv", self.book)["issues"]]
        self.assertEqual(sorted(codes), ["duplicate_id", "unknown_answer", "unknown_segment"])

    def test_example_north_score_counts(self):
        result = audit(EXAMPLES / "responses.csv", self.book)
        rows = [r for r in result["cross_tabs"]
                if r["segment"] == "North" and r["question"] == "service_score"]
        self.assertEqual([r["count"] for r in rows], [0, 1, 1, 0, 2])

    def test_example_south_recommend_counts(self):
        result = audit(EXAMPLES / "responses.csv", self.book)
        rows = [r for r in result["cross_tabs"]
                if r["segment"] == "South" and r["question"] == "recommend"]
        self.assertEqual([(r["count"], r["valid_pct"]) for r in rows],
                         [(1, 50.0), (1, 50.0)])

    def test_north_recommend_completion(self):
        result = audit(EXAMPLES / "responses.csv", self.book)
        entry = next(x for x in result["completion"]
                     if x["segment"] == "North" and x["question"] == "recommend")
        self.assertEqual((entry["respondents"], entry["valid"],
                          entry["missing"], entry["invalid"], entry["completion_pct"]),
                         (4, 3, 0, 1, 75.0))

    def test_every_summary_reconciles(self):
        result = audit(EXAMPLES / "responses.csv", self.book)
        for row in result["completion"]:
            self.assertEqual(row["valid"] + row["missing"] + row["invalid"],
                             row["respondents"])

    def test_unknown_answer_keeps_other_question(self):
        result = self.run_rows("r1,North,5,Maybe\n")
        score = next(r for r in result["completion"] if r["question"] == "service_score"
                     and r["segment"] == "North")
        self.assertEqual(score["valid"], 1)
        self.assertEqual(len(result["issues"]), 1)

    def test_missing_marker_is_not_invalid(self):
        result = self.run_rows("r1,North,NA,Yes\n")
        score = next(r for r in result["completion"] if r["question"] == "service_score"
                     and r["segment"] == "North")
        self.assertEqual((score["missing"], score["invalid"]), (1, 0))

    def test_blank_marker_is_missing(self):
        result = self.run_rows("r1,North,,Yes\n")
        score = next(r for r in result["completion"] if r["question"] == "service_score"
                     and r["segment"] == "North")
        self.assertEqual(score["missing"], 1)

    def test_blank_id_excludes_row(self):
        result = self.run_rows(",North,5,Yes\n")
        self.assertEqual(result["included_respondents"], 0)
        self.assertEqual(result["issues"][0]["code"], "missing_id")

    def test_repeated_id_excludes_later_row(self):
        result = self.run_rows("r1,North,1,Yes\nr1,North,5,No\n")
        self.assertEqual(result["included_respondents"], 1)
        self.assertEqual(result["issues"][0]["code"], "duplicate_id")
        self.assertEqual(next(r for r in result["cross_tabs"] if
                              r["question"] == "service_score" and
                              r["segment"] == "North" and r["answer"] == "1")["count"], 1)

    def test_unknown_segment_excluded(self):
        result = self.run_rows("r1,West,5,Yes\n")
        self.assertEqual(result["included_respondents"], 0)
        self.assertEqual(result["issues"][0]["code"], "unknown_segment")

    def test_duplicate_after_bad_segment_is_excluded(self):
        result = self.run_rows("r1,West,5,Yes\nr1,North,5,Yes\n")
        self.assertEqual(result["included_respondents"], 0)
        self.assertEqual([r["code"] for r in result["issues"]],
                         ["unknown_segment", "duplicate_id"])

    def test_extra_csv_field_is_malformed(self):
        result = self.run_rows("r1,North,5,Yes,unexpected\n")
        self.assertEqual(result["issues"][0]["code"], "malformed_row")

    def test_short_csv_row_is_malformed(self):
        result = self.run_rows("r1,North,5\n")
        self.assertEqual(result["issues"][0]["code"], "malformed_row")

    def test_empty_input_has_zero_denominators(self):
        result = self.run_rows("")
        self.assertEqual(result["rows_read"], 0)
        self.assertTrue(all(r["completion_pct"] == 0 for r in result["completion"]))
        self.assertTrue(all(r["valid_pct"] == 0 for r in result["cross_tabs"]))

    def test_only_missing_response_has_zero_valid_percentage(self):
        result = self.run_rows("r1,North,,NA\n")
        rows = [r for r in result["cross_tabs"] if r["segment"] == "North"]
        self.assertTrue(all(row["valid_pct"] == 0 for row in rows))

    def test_trim_whitespace(self):
        result = self.run_rows(" r1 , North , 5 , Yes \n")
        self.assertEqual(result["included_respondents"], 1)
        self.assertFalse(result["issues"])

    def test_csv_bom_is_supported(self):
        path = self.work / "bom.csv"
        path.write_text("\ufeffresponse_id,region,service_score,recommend\n"
                        "r1,North,5,Yes\n", encoding="utf-8")
        self.assertEqual(audit(path, self.book)["included_respondents"], 1)

    def test_missing_required_column_rejected(self):
        path = self.work / "bad.csv"
        path.write_text("response_id,region,recommend\nr1,North,Yes\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Missing CSV columns"):
            audit(path, self.book)

    def test_duplicate_header_rejected(self):
        path = self.work / "bad.csv"
        path.write_text("response_id,region,service_score,recommend,recommend\n",
                        encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unique header"):
            audit(path, self.book)

    def test_export_writes_csv_and_json(self):
        result = audit(EXAMPLES / "responses.csv", self.book)
        export(result, self.work / "reports")
        with (self.work / "reports" / "cross_tabs.csv").open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 14)
        saved = json.loads((self.work / "reports" / "audit.json").read_text())
        self.assertEqual(saved["included_respondents"], 7)
        self.assertNotIn("cross_tabs", saved)

    def test_export_is_deterministic(self):
        result = audit(EXAMPLES / "responses.csv", self.book)
        export(result, self.work / "reports")
        first = (self.work / "reports" / "cross_tabs.csv").read_bytes()
        export(result, self.work / "reports")
        self.assertEqual(first, (self.work / "reports" / "cross_tabs.csv").read_bytes())

    def test_cli_success(self):
        command = [sys.executable, str(ROOT / "survey_audit.py"),
                   "--responses", str(EXAMPLES / "responses.csv"),
                   "--codebook", str(EXAMPLES / "codebook.json"),
                   "--output", str(self.work / "reports")]
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Read 9 rows", process.stdout)

    def test_cli_missing_file_fails(self):
        process = subprocess.run([sys.executable, str(ROOT / "survey_audit.py"),
            "--responses", str(self.work / "missing.csv"),
            "--codebook", str(EXAMPLES / "codebook.json"),
            "--output", str(self.work / "reports")], capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 2)
        self.assertIn("Input error:", process.stderr)

    def save_codebook(self, modify):
        obj = json.loads((EXAMPLES / "codebook.json").read_text())
        modify(obj)
        path = self.work / "codebook.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def test_codebook_segment_duplicates_rejected(self):
        path = self.save_codebook(lambda obj: obj.update(segments=["North", "North"]))
        with self.assertRaises(CodebookError):
            read_codebook(path)

    def test_codebook_choice_duplicates_rejected(self):
        path = self.save_codebook(lambda obj: obj["questions"]["recommend"].update(choices=["Yes", "Yes"]))
        with self.assertRaises(CodebookError):
            read_codebook(path)

    def test_codebook_choice_overlaps_missing_rejected(self):
        path = self.save_codebook(lambda obj: obj["questions"]["recommend"].update(missing=["", "Yes"]))
        with self.assertRaises(CodebookError):
            read_codebook(path)

    def test_codebook_same_id_segment_rejected(self):
        path = self.save_codebook(lambda obj: obj.update(segment_column="response_id"))
        with self.assertRaises(CodebookError):
            read_codebook(path)

    def test_codebook_question_same_as_id_rejected(self):
        path = self.save_codebook(lambda obj: obj.update(questions={"response_id": {"choices": ["1"]}}))
        with self.assertRaises(CodebookError):
            read_codebook(path)

    def test_codebook_requires_questions(self):
        path = self.save_codebook(lambda obj: obj.update(questions={}))
        with self.assertRaises(CodebookError):
            read_codebook(path)

    def test_codebook_requires_segments(self):
        path = self.save_codebook(lambda obj: obj.update(segments=[]))
        with self.assertRaises(CodebookError):
            read_codebook(path)

    def test_codebook_defaults_missing_codes(self):
        path = self.save_codebook(lambda obj: obj["questions"]["recommend"].pop("missing"))
        book = read_codebook(path)
        q = next(q for q in book.questions if q.name == "recommend")
        self.assertEqual(q.missing, ("", "NA"))

    def test_codebook_allows_no_missing_codes(self):
        path = self.save_codebook(lambda obj: obj["questions"]["recommend"].update(missing=[]))
        book = read_codebook(path)
        q = next(q for q in book.questions if q.name == "recommend")
        self.assertEqual(q.missing, ())

    def test_codebook_trailing_space_rejected(self):
        path = self.save_codebook(lambda obj: obj.update(segments=["North ", "South"]))
        with self.assertRaises(CodebookError):
            read_codebook(path)

    def test_codebook_empty_choice_rejected(self):
        path = self.save_codebook(lambda obj: obj["questions"]["recommend"].update(choices=["", "Yes"]))
        with self.assertRaises(CodebookError):
            read_codebook(path)


if __name__ == "__main__":
    unittest.main()
