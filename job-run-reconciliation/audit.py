"""Reconcile scheduled batch jobs with observed runs from offline CSV files."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

EXPECTED_FIELDS = ("slot_id", "scheduled_at")
ACTUAL_FIELDS = ("slot_id", "started_at", "status")
VALID_STATUSES = {"success", "failed", "cancelled"}


@dataclass(frozen=True)
class Issue:
    slot_id: str
    code: str
    detail: str


def timestamp(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Timestamp must contain an explicit UTC offset")
    return dt


def audit_rows(
    expected_rows: Iterable[dict[str, str]],
    observed_rows: Iterable[dict[str, str]],
    tolerance_minutes: int = 15,
) -> list[Issue]:
    if tolerance_minutes < 0 or tolerance_minutes > 1440:
        raise ValueError("Tolerance must be between 0 and 1440 minutes")

    issues: list[Issue] = []
    expected: dict[str, datetime] = {}
    observed: dict[str, tuple[datetime, str]] = {}

    for row in expected_rows:
        slot = (row.get("slot_id") or "").strip()
        stamp = (row.get("scheduled_at") or "").strip()
        if not slot:
            issues.append(Issue("", "invalid_expected_id", "Empty slot ID"))
            continue
        try:
            planned = timestamp(stamp)
        except ValueError:
            issues.append(Issue(slot, "invalid_scheduled_time", stamp))
            continue
        if slot in expected:
            issues.append(Issue(slot, "duplicate_expected", "Repeated schedule row"))
        else:
            expected[slot] = planned

    for row in observed_rows:
        slot = (row.get("slot_id") or "").strip()
        stamp = (row.get("started_at") or "").strip()
        status = (row.get("status") or "").strip().lower()
        if not slot:
            issues.append(Issue("", "invalid_observed_id", "Empty slot ID"))
            continue
        try:
            started = timestamp(stamp)
        except ValueError:
            issues.append(Issue(slot, "invalid_started_time", stamp))
            continue
        if status not in VALID_STATUSES:
            issues.append(Issue(slot, "invalid_status", status))
            continue
        if slot in observed:
            issues.append(Issue(slot, "duplicate_observed", "Repeated run row"))
        else:
            observed[slot] = (started, status)

    tolerance = timedelta(minutes=tolerance_minutes)
    for slot, planned in expected.items():
        run = observed.get(slot)
        if run is None:
            issues.append(Issue(slot, "missing_run", planned.isoformat()))
            continue
        started, status = run
        if status != "success":
            issues.append(Issue(slot, "unsuccessful_run", status))
        if started > planned + tolerance:
            issues.append(Issue(slot, "late_start", f"planned={planned.isoformat()}, started={started.isoformat()}"))

    for slot in observed:
        if slot not in expected:
            issues.append(Issue(slot, "unexpected_run", "No corresponding schedule row"))

    return sorted(issues, key=lambda item: (item.slot_id, item.code))


def audit_files(plan: Path, runs: Path, report: Path, tolerance_minutes: int) -> list[Issue]:
    if len({p.resolve() for p in (plan, runs, report)}) != 3:
        raise ValueError("Input and output paths must differ")

    def load(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not set(required).issubset(reader.fieldnames or []):
                raise ValueError(f"Missing columns in {path.name}")
            return list(reader)

    issues = audit_rows(load(plan, EXPECTED_FIELDS), load(runs, ACTUAL_FIELDS),
                        tolerance_minutes)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["slot_id", "code", "detail"])
        for issue in issues:
            writer.writerow([issue.slot_id, issue.code, issue.detail])
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("runs", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--tolerance-minutes", type=int, default=15)
    args = parser.parse_args(argv)
    try:
        issues = audit_files(args.plan, args.runs, args.report, args.tolerance_minutes)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"Found {len(issues)} issue(s); report: {args.report}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
