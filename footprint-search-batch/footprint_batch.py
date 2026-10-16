"""Offline, deterministic batch search consolidation for synthetic website data."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def read_locations(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"town", "area_code", "postcodes"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Locations CSV needs town,area_code,postcodes headers")
        locations = []
        for number, row in enumerate(reader, 2):
            town = (row["town"] or "").strip()
            area = (row["area_code"] or "").strip()
            postcodes = [part.strip() for part in (row["postcodes"] or "").split("|")]
            if not town or not area or not any(postcodes):
                raise ValueError(f"Invalid location on CSV line {number}")
            locations.append({"town": town, "area_code": area, "postcodes": "|".join(p for p in postcodes if p)})
    if not locations:
        raise ValueError("Locations CSV is empty")
    return locations


def read_footprints(path: Path) -> list[str]:
    footprints = list(dict.fromkeys(line.strip() for line in
                                    path.read_text(encoding="utf-8").splitlines()
                                    if line.strip() and not line.lstrip().startswith("#")))
    if not footprints:
        raise ValueError("At least one search footprint is needed")
    return footprints


def plan_queries(locations: list[dict[str, str]], footprints: list[str]) -> list[tuple[str, str, str]]:
    """Yield (town, footprint, search term) in deterministic order, without repeats."""
    planned: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in locations:
        terms = [row["town"], row["area_code"], *row["postcodes"].split("|")]
        for footprint in footprints:
            for term in terms:
                item = (row["town"], footprint, term)
                if item not in seen:
                    seen.add(item)
                    planned.append(item)
    return planned


def load_fixture(path: Path) -> dict[str, list[dict[str, str]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Search fixture must be a JSON object")
    for key, items in data.items():
        if not isinstance(key, str) or not isinstance(items, list):
            raise ValueError("Each fixture key must map to a list")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str) or not isinstance(item.get("title"), str):
                raise ValueError(f"Invalid search result under {key!r}")
    return data


def normalize_url(value: str) -> str:
    """Canonicalize for this demonstration: ignore scheme, fragment and query string."""
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Expected an absolute HTTP(S) URL")
    if parts.username or parts.password or parts.port is not None:
        raise ValueError("Credentials and explicit ports are not supported")
    hostname = parts.hostname.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if not hostname or " " in hostname:
        raise ValueError("Invalid website hostname")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", hostname, path, "", ""))


def safe_csv_cell(value: str) -> str:
    """Protect spreadsheet users from CSV formula evaluation."""
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def consolidate(locations: list[dict[str, str]], footprints: list[str],
                fixture: dict[str, list[dict[str, str]]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    records: dict[str, dict[str, str]] = {}
    counts: Counter[str] = Counter()
    for town, footprint, term in plan_queries(locations, footprints):
        counts["queries"] += 1
        for item in fixture.get(f"{footprint}|{term}", []):
            counts["hits"] += 1
            try:
                url = normalize_url(item["url"])
            except ValueError:
                counts["invalid_urls"] += 1
                continue
            if url in records:
                counts["duplicate_hits"] += 1
                continue
            records[url] = {"url": url, "title": item["title"], "town": town,
                            "footprint": footprint, "matched_term": term}
    rows = [records[url] for url in sorted(records)]
    result = {key: counts[key] for key in ("queries", "hits", "unique_sites", "duplicate_hits", "invalid_urls")}
    result["unique_sites"] = len(rows)
    return rows, result


def write_report(rows: list[dict[str, str]], counts: dict[str, int], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    columns = ["url", "title", "town", "footprint", "matched_term"]
    with (out_dir / "sites.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: safe_csv_cell(row[key]) for key in columns} for row in rows)
    (out_dir / "summary.json").write_text(
        json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consolidate synthetic search API results")
    parser.add_argument("--locations", type=Path, required=True)
    parser.add_argument("--footprints", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rows, summary = consolidate(read_locations(args.locations),
                                    read_footprints(args.footprints), load_fixture(args.fixture))
        write_report(rows, summary, args.output)
    except (OSError, ValueError, csv.Error, json.JSONDecodeError) as exc:
        parser.exit(2, f"Input error: {exc}\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
