"""Command-line entry point for the payroll quality audit."""
import argparse
import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .audit import analyze
from .output import save_reports


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit a monthly payroll CSV.")
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--issues", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--max-overtime", default="20")
    args = parser.parse_args(argv)
    locations = [args.input_csv.resolve(), args.issues.resolve(), args.summary.resolve()]
    if len(set(locations)) != len(locations):
        parser.error("Input and output paths must differ")
    try:
        overtime_limit = Decimal(args.max_overtime)
        headers, flagged, summary = analyze(args.input_csv, overtime_limit)
        save_reports(headers, flagged, summary, args.issues, args.summary)
    except (OSError, ValueError, InvalidOperation, UnicodeError, csv.Error) as exc:
        parser.exit(2, "error: " + str(exc) + "\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
