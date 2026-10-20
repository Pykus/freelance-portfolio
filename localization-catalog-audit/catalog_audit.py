"""Offline localization QA for teams shipping translated product text.

Checks missing/extra keys and mismatched Python-style named placeholders.
Standard-library only; fixture text is fictional.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import string
from collections import Counter
from pathlib import Path

KEY_RE = re.compile(r"[a-z][a-z0-9_.-]*\Z")
FIELD_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
LOCALE_RE = re.compile(r"[a-z]{2}(?:-[A-Z]{2})?\Z")
COLUMNS = ["locale", "key", "issue", "source", "translation", "details"]


def read_catalog(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"key", "text"}.issubset(reader.fieldnames):
            raise ValueError(f"{path.name}: requires key,text CSV headers")
        result: dict[str, str] = {}
        for line, row in enumerate(reader, 2):
            if None in row or row.get("key") is None or row.get("text") is None:
                raise ValueError(f"{path.name}: malformed CSV row {line}")
            key = row["key"].strip()
            if not KEY_RE.fullmatch(key):
                raise ValueError(f"{path.name}: invalid key on row {line}")
            if key in result:
                raise ValueError(f"{path.name}: duplicate key '{key}' on row {line}")
            result[key] = row["text"]
        return result


def placeholders(text: str) -> Counter[str]:
    """Parse escaped braces and named placeholders; reject unsafe expressions."""
    result: Counter[str] = Counter()
    for _, field, format_spec, conversion in string.Formatter().parse(text):
        if field is None:
            continue
        if not FIELD_RE.fullmatch(field) or conversion is not None or format_spec:
            raise ValueError("Only simple {name} placeholders are supported")
        result[field] += 1
    return result


def audit(source: dict[str, str], target: dict[str, str],
          locale: str) -> tuple[list[dict[str, str]], dict]:
    if not LOCALE_RE.fullmatch(locale):
        raise ValueError("Locale must look like es or pl-PL")
    for key, text in source.items():
        try:
            placeholders(text)
        except ValueError as exc:
            raise ValueError(f"Base catalog key '{key}': {exc}") from exc

    issues: list[dict[str, str]] = []

    def add(key: str, issue: str, details: str) -> None:
        issues.append({
            "locale": locale, "key": key, "issue": issue,
            "source": source.get(key, ""), "translation": target.get(key, ""),
            "details": details,
        })

    for key in sorted(source):
        if key not in target:
            add(key, "missing_key", "No target-language entry for this source key")
            continue
        translated = target[key]
        if not translated.strip():
            add(key, "empty_translation", "Translation is blank")
            continue
        try:
            expected = placeholders(source[key])
            found = placeholders(translated)
        except ValueError as exc:
            add(key, "invalid_format", str(exc))
            continue
        if expected != found:
            add(key, "placeholder_mismatch",
                f"Expected placeholders {dict(sorted(expected.items()))}; "
                f"found {dict(sorted(found.items()))}")

    for key in sorted(target.keys() - source.keys()):
        add(key, "unexpected_key", "Target catalog has no matching source entry")

    issues.sort(key=lambda row: (row["key"], row["issue"]))
    by_code = Counter(row["issue"] for row in issues)
    summary = {
        "locale": locale,
        "source_keys": len(source),
        "target_keys": len(target),
        "issue_count": len(issues),
        "issues_by_code": dict(sorted(by_code.items())),
    }
    return issues, summary


def safe_spreadsheet(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export(issues: list[dict[str, str]], summary: dict, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "issues.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({
            column: safe_spreadsheet(row[column]) for column in COLUMNS
        } for row in issues)
    (folder / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit translated CSV catalogs against their source keys")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--locale", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        base = read_catalog(args.source)
        translated = read_catalog(args.target)
        problems, summary = audit(base, translated, args.locale)
        export(problems, summary, args.output)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"Input error: {exc}\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
