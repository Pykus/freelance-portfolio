"""Deterministic, offline audit of booking overlaps and input quality."""

from __future__ import annotations

import csv
import heapq
import json
import os
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REQUIRED_FIELDS = (
    "booking_id", "resource_id", "start_at", "end_at", "status"
)
VALID_STATUSES = frozenset({"scheduled", "confirmed", "cancelled"})


class SchemaError(ValueError):
    """The input file cannot be interpreted as a booking dataset."""


@dataclass(frozen=True, slots=True)
class Booking:
    row_number: int
    booking_id: str
    resource_id: str
    start: datetime
    end: datetime
    status: str


@dataclass(frozen=True, slots=True)
class Issue:
    row_number: int
    booking_id: str
    resource_id: str
    code: str


@dataclass(frozen=True, slots=True)
class Conflict:
    first: Booking
    second: Booking
    start: datetime
    end: datetime

    @property
    def overlap_seconds(self) -> int:
        return int((self.end - self.start).total_seconds())


@dataclass(frozen=True, slots=True)
class Audit:
    input_rows: int
    validated_bookings: int
    cancelled_bookings: int
    issues: tuple[Issue, ...]
    conflicts: tuple[Conflict, ...]

    def summary(self) -> dict[str, object]:
        return {
            "input_rows": self.input_rows,
            "validated_bookings": self.validated_bookings,
            "cancelled_bookings": self.cancelled_bookings,
            "invalid_rows": len({x.row_number for x in self.issues}),
            "issue_counts": dict(sorted(Counter(x.code for x in self.issues).items())),
            "conflict_pairs": len(self.conflicts),
            "resources_with_conflicts": len({x.first.resource_id.casefold() for x in self.conflicts}),
        }


def _parse_instant(value: str) -> datetime:
    # Explicit numeric offsets (or Z) make comparisons unambiguous at DST changes.
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.utcoffset() is None:
        raise ValueError("An explicit timezone offset is required")
    return instant.astimezone(timezone.utc)


def _normalized_id(text: str) -> str:
    return text.strip().casefold()


def audit_csv(path: str | Path) -> Audit:
    entries: list[Booking] = []
    raw_rows: list[tuple[int, dict[str, str | None]]] = []
    issues_by_row: dict[int, set[str]] = defaultdict(set)
    ids: dict[str, list[int]] = defaultdict(list)

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames
        if not headers:
            raise SchemaError("No header row")
        if len(headers) != len(set(headers)) or any(not h for h in headers):
            raise SchemaError("Repeated or empty column names")
        missing = sorted(set(REQUIRED_FIELDS) - set(headers))
        if missing:
            raise SchemaError("Missing columns: " + ", ".join(missing))

        for record in reader:
            row = reader.line_num
            raw_rows.append((row, record))
            if None in record or any(record.get(key) is None for key in REQUIRED_FIELDS):
                issues_by_row[row].add("MALFORMED_ROW")
            booking_id = (record.get("booking_id") or "").strip()
            resource_id = (record.get("resource_id") or "").strip()
            if not booking_id:
                issues_by_row[row].add("MISSING_BOOKING_ID")
            else:
                ids[_normalized_id(booking_id)].append(row)
            if not resource_id:
                issues_by_row[row].add("MISSING_RESOURCE_ID")

            status = (record.get("status") or "").strip().casefold()
            if status not in VALID_STATUSES:
                issues_by_row[row].add("INVALID_STATUS")

            start = end = None
            for field in ("start_at", "end_at"):
                try:
                    instant = _parse_instant((record.get(field) or "").strip())
                    if field == "start_at":
                        start = instant
                    else:
                        end = instant
                except ValueError:
                    issues_by_row[row].add("INVALID_" + field.upper())
            if start is not None and end is not None and end <= start:
                issues_by_row[row].add("NONPOSITIVE_DURATION")
            if not issues_by_row[row]:
                assert start is not None and end is not None
                entries.append(Booking(row, booking_id, resource_id, start, end, status))

    # Mark *all* occurrences, not just the second duplicate.
    for rows in ids.values():
        if len(rows) > 1:
            for row in rows:
                issues_by_row[row].add("DUPLICATE_BOOKING_ID")

    eligible = [b for b in entries if not issues_by_row[b.row_number]]
    booked = [b for b in eligible if b.status != "cancelled"]
    conflicts = _find_conflicts(booked)
    issue_rows = []
    for row, record in raw_rows:
        for code in sorted(issues_by_row[row]):
            issue_rows.append(Issue(row, (record.get("booking_id") or ""),
                                    (record.get("resource_id") or ""), code))

    return Audit(
        input_rows=len(raw_rows),
        validated_bookings=len(booked),
        cancelled_bookings=sum(b.status == "cancelled" for b in eligible),
        issues=tuple(issue_rows),
        conflicts=tuple(conflicts),
    )


def _find_conflicts(bookings: Iterable[Booking]) -> list[Conflict]:
    groups: dict[str, list[Booking]] = defaultdict(list)
    for item in bookings:
        groups[_normalized_id(item.resource_id)].append(item)

    results: list[Conflict] = []
    for resource in sorted(groups):
        # Sweep by start time; a min-heap evicts intervals already ended.
        # Comparing the remaining active bookings emits every overlapping pair.
        heap: list[tuple[datetime, int]] = []
        active: dict[int, Booking] = {}
        for current in sorted(groups[resource], key=lambda b: (b.start, b.row_number)):
            while heap and heap[0][0] <= current.start:
                _, row = heapq.heappop(heap)
                active.pop(row, None)
            for previous in active.values():
                overlap_end = min(previous.end, current.end)
                if overlap_end > current.start:
                    results.append(Conflict(previous, current, current.start, overlap_end))
            active[current.row_number] = current
            heapq.heappush(heap, (current.end, current.row_number))

    return sorted(results, key=lambda c: (
        c.first.resource_id.casefold(), c.start, c.first.row_number, c.second.row_number
    ))


def _spreadsheet_safe(value: str) -> str:
    # CSV quoting alone does not prevent Excel/LibreOffice formula execution.
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _atomic_write(path: Path, write) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent,
            prefix="." + path.name + ".", suffix=".tmp", delete=False
        ) as handle:
            temp_path = handle.name
            write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def export_reports(audit: Audit, conflicts: str | Path, issues: str | Path,
                   summary: str | Path, *, input_file: str | Path | None = None) -> None:
    destinations = [Path(p).resolve() for p in (conflicts, issues, summary)]
    if len(set(destinations)) != 3:
        raise ValueError("Output paths must be distinct")
    if input_file is not None and Path(input_file).resolve() in destinations:
        raise ValueError("An output would overwrite the input dataset")

    def write_conflicts(handle):
        writer = csv.writer(handle)
        writer.writerow(("first_row", "second_row", "resource_id", "first_booking_id",
                         "second_booking_id", "overlap_start_utc", "overlap_end_utc", "overlap_seconds"))
        for c in audit.conflicts:
            writer.writerow((c.first.row_number, c.second.row_number,
                             _spreadsheet_safe(c.first.resource_id),
                             _spreadsheet_safe(c.first.booking_id),
                             _spreadsheet_safe(c.second.booking_id),
                             c.start.isoformat(), c.end.isoformat(), c.overlap_seconds))

    def write_issues(handle):
        writer = csv.writer(handle)
        writer.writerow(("row_number", "booking_id", "resource_id", "issue_code"))
        for issue in audit.issues:
            writer.writerow((issue.row_number, _spreadsheet_safe(issue.booking_id),
                             _spreadsheet_safe(issue.resource_id), issue.code))

    _atomic_write(destinations[0], write_conflicts)
    _atomic_write(destinations[1], write_issues)
    _atomic_write(destinations[2], lambda handle: json.dump(audit.summary(), handle, indent=2, sort_keys=True))
