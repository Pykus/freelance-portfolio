"""Command-line entry point for the booking audit."""

import argparse
from pathlib import Path

from .core import SchemaError, audit_csv, export_reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit timezone-aware resource bookings for overlaps")
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--conflicts", type=Path, default=Path("conflicts.csv"))
    parser.add_argument("--issues", type=Path, default=Path("issues.csv"))
    parser.add_argument("--summary", type=Path, default=Path("summary.json"))
    args = parser.parse_args(argv)
    try:
        result = audit_csv(args.input_csv)
        export_reports(result, args.conflicts, args.issues, args.summary, input_file=args.input_csv)
    except (SchemaError, ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Reviewed {result.input_rows} rows; {len(result.conflicts)} overlaps; "
          f"{result.summary()['invalid_rows']} invalid rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
