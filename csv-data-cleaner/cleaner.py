"""Dependency-free CSV cleaning utility for small business exports."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def clean_csv(source, destination, *, required=None, dedupe_by=None):
    """Normalize whitespace, discard blank rows, and remove duplicate records.

    Returns a dictionary of processing statistics. All columns remain strings,
    preserving leading zeros in identifiers and postal codes.
    """
    required = required or []
    with open(source, "r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("CSV must contain a header row")
        fields = [field.strip() for field in reader.fieldnames]
        if len(set(fields)) != len(fields):
            raise ValueError("Duplicate column names after trimming whitespace")
        missing = set(required + (dedupe_by or [])) - set(fields)
        if missing:
            raise ValueError("Unknown columns: " + ", ".join(sorted(missing)))
        rows = []
        seen = set()
        stats = Counter(read=0, written=0, blank=0, missing_required=0, duplicates=0)
        for raw in reader:
            stats["read"] += 1
            if None in raw:
                raise ValueError(f"Row {stats['read']} has more fields than header")
            row = {key.strip(): (value or "").strip() for key, value in raw.items()}
            if not any(row.values()):
                stats["blank"] += 1
                continue
            if any(not row[column] for column in required):
                stats["missing_required"] += 1
                continue
            key = tuple(row[col].casefold() for col in (dedupe_by or fields))
            if key in seen:
                stats["duplicates"] += 1
                continue
            seen.add(key)
            rows.append(row)
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    stats["written"] = len(rows)
    return dict(stats)


def main():
    parser = argparse.ArgumentParser(description="Clean and deduplicate CSV exports.")
    parser.add_argument("source", help="Input CSV file")
    parser.add_argument("destination", help="Output CSV file")
    parser.add_argument("--required", nargs="*", default=[], help="Columns that must not be empty")
    parser.add_argument("--dedupe-by", nargs="+", help="Columns used as duplicate key")
    args = parser.parse_args()
    print(json.dumps(clean_csv(args.source, args.destination,
                               required=args.required, dedupe_by=args.dedupe_by), indent=2))


if __name__ == "__main__":
    main()
