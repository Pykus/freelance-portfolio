"""Build an auditable list of business websites from repeatable source-code searches.

This tool does NOT search the internet. It plans PublicWWW queries and processes
either manually recorded results or deterministic example results.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
SITE_COLUMNS = [
    "domain", "example_url", "title", "matched_footprints",
    "matched_towns", "matched_terms", "search_queries", "hit_count",
]
QUERY_COLUMNS = ["town", "footprint", "location_term", "query"]


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
            locations.append({
                "town": town, "area_code": area,
                "postcodes": "|".join(part for part in postcodes if part),
            })
    if not locations:
        raise ValueError("Locations CSV is empty")
    return locations


def read_footprints(path: Path) -> list[str]:
    footprints = list(dict.fromkeys(
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ))
    if not footprints:
        raise ValueError("At least one search footprint is needed")
    return footprints


def plan_queries(locations: list[dict[str, str]],
                 footprints: list[str]) -> list[tuple[str, str, str]]:
    """Return unique (town, source-code footprint, location term) combinations."""
    planned = []
    seen = set()
    for row in locations:
        terms = [row["town"], row["area_code"], *row["postcodes"].split("|")]
        for footprint in footprints:
            for term in terms:
                item = (row["town"], footprint, term)
                if item not in seen:
                    seen.add(item)
                    planned.append(item)
    return planned


def build_query(footprint: str, term: str) -> str:
    """Generate a copy/paste-ready PublicWWW source-code search query."""
    def quoted(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"depth:all site:uk {quoted(footprint)} {quoted(term)}"


def planned_rows(locations: list[dict[str, str]],
                 footprints: list[str]) -> list[dict[str, str]]:
    return [
        {"town": town, "footprint": footprint, "location_term": term,
         "query": build_query(footprint, term)}
        for town, footprint, term in plan_queries(locations, footprints)
    ]


def load_fixture(path: Path) -> dict[str, list[dict[str, str]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Example results must be a JSON object")
    for key, items in data.items():
        if not isinstance(key, str) or not isinstance(items, list):
            raise ValueError("Every example search must map to a list")
        for item in items:
            if (not isinstance(item, dict)
                    or not isinstance(item.get("url"), str)
                    or not isinstance(item.get("title"), str)):
                raise ValueError(f"Invalid example result under {key!r}")
    return data


def fixture_hits(locations: list[dict[str, str]], footprints: list[str],
                 fixture: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    hits = []
    for row in planned_rows(locations, footprints):
        for item in fixture.get(f"{row['footprint']}|{row['location_term']}", []):
            hits.append({"query": row["query"], "url": item["url"],
                         "title": item["title"]})
    return hits


def read_results_csv(path: Path) -> list[dict[str, str]]:
    """Read copied search results. Query must match a row in queries.csv."""
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"query", "url"}.issubset(reader.fieldnames):
            raise ValueError("Results CSV requires query,url columns (title optional)")
        hits = []
        for number, row in enumerate(reader, 2):
            if not row.get("query") or not row.get("url"):
                raise ValueError(f"Missing query or URL on results CSV line {number}")
            hits.append({
                "query": row["query"].strip(),
                "url": row["url"].strip(),
                "title": (row.get("title") or "").strip(),
            })
    return hits


def normalize_url(value: str) -> str:
    """Normalize a URL but keep its page path as evidence of the matching page."""
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Expected an absolute HTTP(S) URL")
    if parts.username or parts.password or parts.port is not None:
        raise ValueError("Credentials and explicit ports are not supported")
    hostname = parts.hostname.lower().rstrip(".")
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if (not hostname or "." not in hostname or ".." in hostname
            or any(char.isspace() for char in hostname)
            or any(char in hostname for char in "/\\@#?")):
        raise ValueError("Invalid website hostname")
    return urlunsplit(("https", hostname, parts.path.rstrip("/") or "/", "", ""))


def safe_csv_cell(value: str) -> str:
    """Avoid spreadsheet formula evaluation when a human opens exported CSV."""
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def consolidate_hits(locations: list[dict[str, str]], footprints: list[str],
                     hits: list[dict[str, str]]
                     ) -> tuple[list[dict[str, str]], dict[str, int]]:
    plans = planned_rows(locations, footprints)
    lookup = {row["query"]: row for row in plans}
    groups: dict[str, dict] = {}
    counts: Counter[str] = Counter()
    counts["queries"] = len(plans)
    for hit in hits:
        query = hit["query"]
        if query not in lookup:
            raise ValueError(
                f"Unknown search query {query!r}; copy it exactly from queries.csv")
        counts["hits"] += 1
        try:
            url = normalize_url(hit["url"])
        except ValueError:
            counts["invalid_urls"] += 1
            continue
        domain = urlsplit(url).hostname
        assert domain is not None
        plan = lookup[query]
        if domain not in groups:
            groups[domain] = {
                "domain": domain,
                "example_url": url,
                "title": hit["title"],
                "matched_footprints": set(),
                "matched_towns": set(),
                "matched_terms": set(),
                "search_queries": set(),
                "hit_count": 0,
            }
        else:
            counts["duplicate_hits"] += 1
        record = groups[domain]
        record["hit_count"] += 1
        if not record["title"] and hit["title"]:
            record["title"] = hit["title"]
        record["matched_footprints"].add(plan["footprint"])
        record["matched_towns"].add(plan["town"])
        record["matched_terms"].add(plan["location_term"])
        record["search_queries"].add(query)
    rows = []
    for domain in sorted(groups):
        record = groups[domain]
        rows.append({
            key: " | ".join(sorted(record[key])) if isinstance(record[key], set)
            else record[key]
            for key in SITE_COLUMNS
        })
    counts["unique_sites"] = len(rows)
    return rows, {key: counts[key] for key in
                  ("queries", "hits", "unique_sites", "duplicate_hits", "invalid_urls")}


def consolidate(locations: list[dict[str, str]], footprints: list[str],
                fixture: dict[str, list[dict[str, str]]]
                ) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Compatibility helper for offline example results."""
    return consolidate_hits(locations, footprints,
                            fixture_hits(locations, footprints, fixture))


def write_csv(path: Path, columns: list[str],
              rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({
            key: safe_csv_cell(str(row[key])) for key in columns
        } for row in rows)


def write_plan(locations: list[dict[str, str]],
               footprints: list[str], out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = planned_rows(locations, footprints)
    write_csv(out_dir / "queries.csv", QUERY_COLUMNS, rows)
    return len(rows)


def write_report(rows: list[dict[str, str]], counts: dict[str, int],
                 out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "sites.csv", SITE_COLUMNS, rows)
    (out_dir / "summary.json").write_text(
        json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan UK website-source searches and consolidate copied results")
    parser.add_argument("--locations", type=Path,
                        default=ROOT / "examples/locations.csv")
    parser.add_argument("--footprints", type=Path,
                        default=ROOT / "examples/footprints.txt")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--plan-only", action="store_true",
                        help="Write queries.csv without processing any search results")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--demo", action="store_true",
                       help="Run the fictional example without web access")
    group.add_argument("--fixture", type=Path,
                       help="Process an offline JSON fixture")
    group.add_argument("--results-csv", type=Path,
                       help="Process manually collected query,url,title results")
    args = parser.parse_args(argv)
    if not (args.plan_only or args.demo or args.fixture or args.results_csv):
        parser.error("Choose --demo, --results-csv FILE, --fixture FILE or --plan-only")
    try:
        locations = read_locations(args.locations)
        footprints = read_footprints(args.footprints)
        queries = write_plan(locations, footprints, args.output)
        if args.plan_only:
            print(f"Wrote {queries} copy/paste-ready queries to {args.output / 'queries.csv'}")
            return 0
        if args.demo or args.fixture:
            fixture = load_fixture(args.fixture or ROOT / "examples/mock-results.json")
            hits = fixture_hits(locations, footprints, fixture)
        else:
            hits = read_results_csv(args.results_csv)
        rows, counts = consolidate_hits(locations, footprints, hits)
        write_report(rows, counts, args.output)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"Input error: {exc}\n")
    print(json.dumps(counts, sort_keys=True))
    print(f"Wrote {args.output / 'sites.csv'} and {args.output / 'queries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
