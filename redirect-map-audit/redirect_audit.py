"""Audit planned website migration redirects without sending HTTP requests.

Input is a list of old URLs and a proposed redirect mapping; the output
identifies missing redirects, chains, cycles, and unmapped extra rules.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

URL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
AUDIT_FIELDS = ("old_url", "status", "final_url", "hops")
FINDING_FIELDS = ("severity", "code", "source", "target", "details")


def normalize_url(text: str) -> str:
    """Keep URL scheme/path/query significant; ignore client-side fragments."""
    value = text.strip()
    try:
        url = urlsplit(value)
        hostname = url.hostname
        port = url.port
    except ValueError as exc:
        raise ValueError(f"Malformed URL: {text!r}") from exc
    if (url.scheme.lower() not in ("http", "https") or not hostname
            or url.username is not None or url.password is not None
            or port is not None or not URL_PATTERN.fullmatch(hostname.lower())
            or "." not in hostname or ".." in hostname):
        raise ValueError(f"Expected an absolute HTTP(S) URL without credentials or port: {text!r}")
    return urlunsplit((url.scheme.lower(), hostname.lower(),
                       url.path or "/", url.query, ""))


def read_csv(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError(f"{path.name} must contain columns: {', '.join(required)}")
        records = []
        for number, row in enumerate(reader, start=2):
            if any(not (row.get(field) or "").strip() for field in required):
                raise ValueError(f"{path.name}: missing value on line {number}")
            records.append({field: row[field].strip() for field in required})
    if not records:
        raise ValueError(f"{path.name} contains no records")
    return records


def follow(source: str, rules: dict[str, str]) -> tuple[str, str, int]:
    """Return (classification, final URL or empty string, redirect hops)."""
    if source not in rules:
        return "missing", "", 0
    current = source
    seen = {source}
    hops = 0
    while current in rules:
        current = rules[current]
        hops += 1
        if current in seen:
            return "loop", "", hops
        seen.add(current)
    return ("direct" if hops == 1 else "chained", current, hops)


def audit(inventory: list[dict[str, str]], mappings: list[dict[str, str]]
          ) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    findings: list[dict[str, str]] = []

    def finding(severity: str, code: str, source: str, target: str, details: str) -> None:
        findings.append(dict(severity=severity, code=code, source=source,
                             target=target, details=details))

    old_urls = []
    inventoried = set()
    for item in inventory:
        original = item["old_url"]
        try:
            source = normalize_url(original)
        except ValueError:
            finding("error", "invalid_inventory_url", original, "", "Review the input URL")
            continue
        if source in inventoried:
            finding("warning", "duplicate_inventory_url", source, "", "Listed twice")
            continue
        inventoried.add(source)
        old_urls.append(source)

    rules: dict[str, str] = {}
    for item in mappings:
        try:
            source = normalize_url(item["source"])
            target = normalize_url(item["target"])
        except ValueError:
            finding("error", "invalid_redirect_url", item["source"], item["target"],
                    "Use complete HTTP(S) URLs")
            continue
        if source in rules:
            finding("error", "duplicate_redirect_source", source, target,
                    "First rule retained; remove or resolve this duplicate")
            continue
        rules[source] = target

    rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for source in old_urls:
        status, final, hops = follow(source, rules)
        counts[status] += 1
        rows.append({"old_url": source, "status": status,
                     "final_url": final, "hops": str(hops)})
        if status == "missing":
            finding("error", "missing_redirect", source, "", "No redirect rule for old page")
        elif status == "loop":
            finding("error", "redirect_loop", source, rules[source],
                    "Redirects eventually return to a previously visited URL")
        elif status == "chained":
            finding("warning", "redirect_chain", source, final,
                    f"Requires {hops} redirects; aim for one")

    intermediate_urls = set(rules.values())
    for source in sorted(rules.keys() - inventoried - intermediate_urls):
        finding("warning", "unlisted_source", source, rules[source],
                "Redirect source is not in the old-site inventory")

    findings.sort(key=lambda f: (f["code"], f["source"], f["target"]))
    summary = {
        "inventory_urls": len(old_urls), "redirect_rules": len(rules),
        "direct": counts["direct"], "chained": counts["chained"],
        "loops": counts["loop"], "missing": counts["missing"],
        "findings": len(findings),
    }
    return rows, findings, summary


def safe_cell(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_csv(path: Path, columns: tuple[str, ...],
               rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({column: safe_cell(row[column]) for column in columns}
                         for row in rows)


def run(inventory: Path, redirects: Path, output: Path
        ) -> tuple[dict[str, int], bool]:
    rows, issues, summary = audit(read_csv(inventory, ("old_url",)),
                                  read_csv(redirects, ("source", "target")))
    output.mkdir(parents=True, exist_ok=True)
    export_csv(output / "audit.csv", AUDIT_FIELDS, rows)
    export_csv(output / "findings.csv", FINDING_FIELDS, issues)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    has_errors = any(item["severity"] == "error" for item in issues)
    return summary, has_errors


def main(argv: list[str] | None = None) -> int:
    base = Path(__file__).resolve().parent / "examples"
    parser = argparse.ArgumentParser(
        description="Detect missing redirects, chains, and loops in a migration map")
    parser.add_argument("--inventory", type=Path, default=base / "old-urls.csv")
    parser.add_argument("--redirects", type=Path, default=base / "redirects.csv")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--fail-on-errors", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary, has_errors = run(args.inventory, args.redirects, args.output)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"Input error: {exc}\n")
    print(json.dumps(summary, sort_keys=True))
    print(f"Reports: {args.output / 'audit.csv'}, {args.output / 'findings.csv'}")
    return 1 if args.fail_on_errors and has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
