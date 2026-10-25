import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from audit import FIELDS, assess_rows, assess_file, main


def entry(**kwargs):
    row = {
        "participant_id": "P-001", "sessions_attended": "4",
        "sessions_total": "5", "quiz_percent": "70.00",
    }
    row.update(kwargs)
    return row


class CompletionTests(unittest.TestCase):
    def test_exact_threshold(self):
        r = assess_rows([entry()])
        self.assertEqual(r.issues, [])
        self.assertTrue(r.completions[0].eligible)

    def test_below_attendance(self):
        r = assess_rows([entry(sessions_attended="3")])
        self.assertFalse(r.completions[0].eligible)
        self.assertEqual(r.completions[0].reasons, "low_attendance")

    def test_below_quiz(self):
        self.assertEqual(assess_rows([entry(quiz_percent="69.99")])
                         .completions[0].reasons, "low_quiz")

    def test_both_below(self):
        self.assertEqual(assess_rows([
            entry(sessions_attended="2", quiz_percent="40")])
            .completions[0].reasons, "low_attendance;low_quiz")

    def test_perfect_score(self):
        self.assertTrue(assess_rows([
            entry(sessions_attended="5", quiz_percent="100")]).completions[0].eligible)

    def test_percentage_uses_exact_fraction(self):
        self.assertEqual(str(assess_rows([
            entry(sessions_attended="2", sessions_total="3")])
            .completions[0].attendance_pct), "66.67")

    def test_duplicate_casefold(self):
        r = assess_rows([entry(), entry(participant_id="p-001")])
        self.assertEqual(len(r.completions), 1)
        self.assertEqual(r.issues[0].code, "duplicate_participant")

    def test_empty_id(self):
        self.assertEqual(assess_rows([entry(participant_id="")])
                         .issues[0].code, "missing_field")

    def test_zero_total(self):
        self.assertEqual(assess_rows([entry(sessions_total="0")])
                         .issues[0].code, "invalid_values")

    def test_negative_attendance(self):
        self.assertEqual(assess_rows([entry(sessions_attended="-1")])
                         .issues[0].code, "invalid_values")

    def test_more_attendance_than_sessions(self):
        self.assertEqual(assess_rows([entry(sessions_attended="6")])
                         .issues[0].code, "invalid_values")

    def test_invalid_score(self):
        self.assertEqual(assess_rows([entry(quiz_percent="NaN")])
                         .issues[0].code, "invalid_values")

    def test_fractional_score(self):
        self.assertEqual(assess_rows([entry(quiz_percent="70.001")])
                         .issues[0].code, "invalid_values")

    def test_negative_score(self):
        self.assertEqual(assess_rows([entry(quiz_percent="-1")])
                         .issues[0].code, "invalid_values")

    def test_empty_data(self):
        result = assess_rows([])
        self.assertEqual((len(result.completions), len(result.issues)), (0, 0))

    def test_two_participants(self):
        result = assess_rows([entry(), entry(participant_id="P-002", quiz_percent="50")])
        self.assertEqual(len(result.completions), 2)
        self.assertEqual([r.eligible for r in result.completions], [True, False])

    def test_cli_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp, passed, errors = root/"in.csv", root/"passed.csv", root/"errors.csv"
            with inp.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow(entry())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(inp), str(passed), str(errors)]), 0)
            with passed.open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 1)
            with errors.open(newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 0)

    def test_bad_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp = root/"in.csv"
            inp.write_text("participant_id\nP-001\n")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(inp), str(root/"passed.csv"),
                                       str(root/"errors.csv")]), 2)

    def test_never_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp = root/"in.csv"
            inp.write_text(",".join(FIELDS)+"\n")
            with self.assertRaises(ValueError):
                assess_file(inp, inp, root/"errors.csv")


if __name__ == "__main__":
    unittest.main()
