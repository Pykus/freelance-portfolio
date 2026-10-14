"""Validate a CSV export against a JSON schema using the Python standard library."""
import csv
import json
import sys
from pathlib import Path

TYPES = {"text", "integer", "decimal"}

def validate(csv_path, schema_path):
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    fields = schema["fields"]
    if not isinstance(fields, dict) or not fields or any(t not in TYPES for t in fields.values()):
        raise ValueError("schema fields must map names to text, integer, or decimal")
    errors = []
    count = 0
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return {"rows": 0, "errors": ["missing header"], "valid": False}
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            errors.append("duplicate column names")
        for name in fields:
            if name not in reader.fieldnames:
                errors.append(f"missing column: {name}")
        for line, row in enumerate(reader, 2):
            count += 1
            if None in row:
                errors.append(f"line {line}: extra values")
            for name, kind in fields.items():
                value = row.get(name)
                if value is None or not value.strip():
                    errors.append(f"line {line}: missing {name}")
                    continue
                try:
                    if kind == "integer":
                        if value.strip().lstrip("+-").isdigit() is False:
                            raise ValueError()
                    elif kind == "decimal":
                        from decimal import Decimal
                        if not Decimal(value).is_finite():
                            raise ValueError()
                except Exception:
                    errors.append(f"line {line}: invalid {kind} in {name}")
    return {"rows": count, "errors": errors, "valid": not errors}

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python validate.py data.csv schema.json")
    report = validate(sys.argv[1], sys.argv[2])
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["valid"] else 1)
