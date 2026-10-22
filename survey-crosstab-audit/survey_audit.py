"""Reproducible quality audit and segmented cross-tabs for synthetic survey CSVs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Question:
    name: str
    choices: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class Codebook:
    id_column: str
    segment_column: str
    segments: tuple[str, ...]
    questions: tuple[Question, ...]


class CodebookError(ValueError):
    """Raised for ambiguous or invalid codebook definitions."""


def _names(values: Any, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(values, list) or (not allow_empty and not values):
        raise CodebookError(f"{label} must be a nonempty list")
    if any(not isinstance(v, str) or v != v.strip() for v in values):
        raise CodebookError(f"{label} must contain trimmed strings")
    if len(values) != len(set(values)):
        raise CodebookError(f"{label} contains duplicates")
    if not allow_empty and "" in values:
        raise CodebookError(f"{label} cannot include an empty value")
    return tuple(values)


def read_codebook(path: Path) -> Codebook:
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise CodebookError("Codebook must be a JSON object")
    id_col = data.get("id_column")
    segment_col = data.get("segment_column")
    if not all(isinstance(v, str) and v and v == v.strip()
               for v in (id_col, segment_col)) or id_col == segment_col:
        raise CodebookError("id_column and segment_column must be distinct names")
    segments = _names(data.get("segments"), "segments")
    raw_questions = data.get("questions")
    if not isinstance(raw_questions, dict) or not raw_questions:
        raise CodebookError("questions must be a nonempty mapping")
    questions: list[Question] = []
    for name, specification in raw_questions.items():
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise CodebookError("Question column names must be nonempty and trimmed")
        if name in (id_col, segment_col) or not isinstance(specification, dict):
            raise CodebookError(f"Invalid question column: {name}")
        choices = _names(specification.get("choices"), f"{name}.choices")
        missing = _names(specification.get("missing", ["", "NA"]),
                         f"{name}.missing", allow_empty=True)
        if set(choices) & set(missing):
            raise CodebookError(f"{name}: choices overlap missing codes")
        questions.append(Question(name, choices, missing))
    return Codebook(id_col, segment_col, segments, tuple(questions))


def audit(csv_path: Path, codebook: Codebook) -> dict[str, Any]:
    """Keep valid unique respondents; exclude invalid answers per question only."""
    issues: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    rows_read = included = 0
    segment_responses: Counter[str] = Counter()
    tallies: Counter[tuple[str, str, str]] = Counter()
    missing: Counter[tuple[str, str]] = Counter()
    invalid: Counter[tuple[str, str]] = Counter()
    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {codebook.id_column, codebook.segment_column}
        required.update(q.name for q in codebook.questions)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV needs unique header names")
        if not required.issubset(set(reader.fieldnames)):
            missing_cols = sorted(required - set(reader.fieldnames))
            raise ValueError(f"Missing CSV columns: {', '.join(missing_cols)}")
        for line, record in enumerate(reader, start=2):
            rows_read += 1
            if None in record or any(v is None for v in record.values()):
                issues.append({"line": line, "column": "", "code": "malformed_row",
                               "detail": "Incorrect number of CSV fields"})
                continue
            record = {key: value.strip() for key, value in record.items()}
            identity = record[codebook.id_column]
            segment = record[codebook.segment_column]
            if not identity:
                issues.append({"line": line, "column": codebook.id_column,
                               "code": "missing_id", "detail": "Respondent is excluded"})
                continue
            if identity in seen_ids:
                issues.append({"line": line, "column": codebook.id_column,
                               "code": "duplicate_id", "detail": identity})
                continue
            seen_ids.add(identity)
            if segment not in codebook.segments:
                issues.append({"line": line, "column": codebook.segment_column,
                               "code": "unknown_segment", "detail": segment})
                continue
            included += 1
            segment_responses[segment] += 1
            for question in codebook.questions:
                value = record[question.name]
                key = (segment, question.name)
                if value in question.missing:
                    missing[key] += 1
                elif value in question.choices:
                    tallies[(segment, question.name, value)] += 1
                else:
                    invalid[key] += 1
                    issues.append({"line": line, "column": question.name,
                                   "code": "unknown_answer", "detail": value})

    cross_tabs: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for segment in codebook.segments:
        for q in codebook.questions:
            valid = sum(tallies[(segment, q.name, answer)] for answer in q.choices)
            miss = missing[(segment, q.name)]
            bad = invalid[(segment, q.name)]
            eligible = segment_responses[segment]
            if valid + miss + bad != eligible:
                raise AssertionError("Survey accounting invariant failed")
            summary.append({"segment": segment, "question": q.name,
                            "respondents": eligible, "valid": valid,
                            "missing": miss, "invalid": bad,
                            "completion_pct": round(100.0 * valid / eligible, 2)
                            if eligible else 0.0})
            for answer in q.choices:
                count = tallies[(segment, q.name, answer)]
                cross_tabs.append({"segment": segment, "question": q.name,
                                   "answer": answer, "count": count,
                                   "valid_pct": round(100.0 * count / valid, 2)
                                   if valid else 0.0})
    return {"rows_read": rows_read, "included_respondents": included,
            "excluded_rows": rows_read - included,
            "issues": issues, "completion": summary, "cross_tabs": cross_tabs}


def export(result: dict[str, Any], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "audit.json").write_text(
        json.dumps({key: value for key, value in result.items() if key != "cross_tabs"},
                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (destination / "cross_tabs.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["segment", "question", "answer",
                                                  "count", "valid_pct"])
        writer.writeheader()
        writer.writerows(result["cross_tabs"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.responses, read_codebook(args.codebook))
        export(result, args.output)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, f"Input error: {error}\n")
    print(f"Read {result['rows_read']} rows; included "
          f"{result['included_respondents']}; issues {len(result['issues'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
