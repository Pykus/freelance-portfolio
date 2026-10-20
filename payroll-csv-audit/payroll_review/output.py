"""Write review-ready CSV and JSON reports without partial output files."""
import csv
import json
import os
import tempfile
from pathlib import Path


def safe_spreadsheet_cell(value):
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def atomic_write(destination, write):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=destination.parent,
            prefix="." + destination.name + ".", delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def save_reports(headers, flagged, summary, issues_path, summary_path):
    if Path(issues_path).resolve() == Path(summary_path).resolve():
        raise ValueError("Output paths must differ")

    def write_issues(stream):
        writer = csv.DictWriter(
            stream, fieldnames=["row_number", *headers, "issue_codes"],
            lineterminator="\n",
        )
        writer.writeheader()
        for item in flagged:
            writer.writerow({
                "row_number": item["row_number"],
                **{k: safe_spreadsheet_cell(item["source"][k]) for k in headers},
                "issue_codes": ";".join(sorted(item["issue_codes"])),
            })

    def write_summary(stream):
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write("\n")

    atomic_write(issues_path, write_issues)
    atomic_write(summary_path, write_summary)
