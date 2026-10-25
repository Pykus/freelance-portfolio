"""Audit fictional course completion records using explicit eligibility rules."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

FIELDS = ("participant_id", "sessions_attended", "sessions_total", "quiz_percent")
CENT = Decimal("0.01")
PASS_QUIZ = Decimal("70.00")


@dataclass(frozen=True)
class Completion:
    participant_id: str
    attendance_pct: Decimal
    quiz_percent: Decimal
    eligible: bool
    reasons: str


@dataclass(frozen=True)
class Issue:
    row: int
    participant_id: str
    code: str


@dataclass(frozen=True)
class Assessment:
    completions: list[Completion]
    issues: list[Issue]


def assess_rows(rows: Iterable[dict[str, str]]) -> Assessment:
    completions: list[Completion] = []
    issues: list[Issue] = []
    seen: set[str] = set()
    for rowno, source in enumerate(rows, start=2):
        data = {field: (source.get(field) or "").strip() for field in FIELDS}
        person = data["participant_id"]
        if not all(data.values()):
            issues.append(Issue(rowno, person, "missing_field"))
            continue
        if person.casefold() in seen:
            issues.append(Issue(rowno, person, "duplicate_participant"))
            continue
        seen.add(person.casefold())
        try:
            attended = int(data["sessions_attended"])
            total = int(data["sessions_total"])
            score = Decimal(data["quiz_percent"])
            if (total <= 0 or attended < 0 or attended > total or
                    not score.is_finite() or score < 0 or score > 100 or
                    score != score.quantize(CENT)):
                raise ValueError("Invalid range or precision")
        except (ValueError, InvalidOperation):
            issues.append(Issue(rowno, person, "invalid_values"))
            continue
        attendance_ok = 5 * attended >= 4 * total
        quiz_ok = score >= PASS_QUIZ
        percentage = (Decimal(100 * attended) / Decimal(total)).quantize(CENT)
        reasons = ";".join(
            name for ok, name in ((attendance_ok, "low_attendance"),
                                   (quiz_ok, "low_quiz")) if not ok
        )
        completions.append(Completion(
            person, percentage, score, attendance_ok and quiz_ok, reasons,
        ))
    return Assessment(completions, issues)


def assess_file(source: Path, results: Path, errors: Path) -> Assessment:
    if len({p.resolve() for p in (source, results, errors)}) != 3:
        raise ValueError("Paths must all be different")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("Input CSV missing required headers")
        assessment = assess_rows(reader)
    results.parent.mkdir(parents=True, exist_ok=True)
    errors.parent.mkdir(parents=True, exist_ok=True)
    with results.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["participant_id", "attendance_pct", "quiz_percent",
                         "eligible", "reasons"])
        for record in assessment.completions:
            writer.writerow([record.participant_id, record.attendance_pct,
                             record.quiz_percent, str(record.eligible).lower(),
                             record.reasons])
    with errors.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row", "participant_id", "code"])
        for item in assessment.issues:
            writer.writerow([item.row, item.participant_id, item.code])
    return assessment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("errors", type=Path)
    args = parser.parse_args(argv)
    try:
        assessment = assess_file(args.source, args.results, args.errors)
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"Assessed {len(assessment.completions)} records; "
          f"{len(assessment.issues)} invalid rows")
    return 1 if assessment.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
