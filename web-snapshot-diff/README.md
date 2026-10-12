# HTML Catalog Change Tracker

Track additions, price/title updates, unchanged listings and removals across saved HTML catalog snapshots. This independent Python + SQLite demonstration uses **only fictional product data** and performs **no network requests**.

## Problem and solution

A team receives periodic HTML snapshots from an authorized source and needs a reproducible answer to: *What changed since the previous capture?* Instead of comparing raw HTML (where formatting may change), this tool extracts a small structured catalog, checks data quality, records immutable versions in SQLite, and writes a machine-readable difference report.

The example input contract is explicit: each product is an `<article data-item-id="...">` with one `<h2>` title and one `<span class="price">$12.50</span>`. Prices are converted to **integer cents** to avoid floating-point errors. Identifiers remain strings, preserving leading zeros. Products are sorted by identifier to make reports deterministic.

## Requirements

Python **3.10+**, SQLite (bundled with Python) and no third-party packages. No API keys, credentials, external services or live website access are needed.

## Run the complete example

From this directory:

    python monitor.py --html examples/day-01.html --database output/history.sqlite3 --source demo-catalog --snapshot day-01 --output output/report-day-01.json
    python monitor.py --html examples/day-02.html --database output/history.sqlite3 --source demo-catalog --snapshot day-02 --output output/report-day-02.json

Both commands create the necessary output directories and store history in the **same SQLite database**. The first run sees all three fictional products as added; the second compares the next snapshot against the first.

### Example input changes

| ID | First snapshot | Second snapshot | Classification |
| --- | --- | --- | --- |
| A-100 | Alpine Widget, $12.50 | Alpine Widget, $12.50 | unchanged |
| B-200 | Amber Adapter, $7.00 | Amber Adapter, $6.50 | updated |
| C-300 | absent | Cobalt Cable, $3.25 | added |
| D-400 | Dove Dock, $25.00 | absent | removed |

Both full HTML input files are versioned: [day-01](examples/day-01.html) and [day-02](examples/day-02.html).

### Actual example outputs

The second command prints a compact JSON summary:

    {"snapshot": "day-02", "counts": {"added": 1, "updated": 1, "removed": 1, "unchanged": 1}, "already_recorded": false}

The output/report-day-02.json file contains source, snapshot, already_recorded, current_count, all four count values, a sorted changes array with before and after objects, and a current_items array. For B-200, before.price_cents = 700 and after.price_cents = 650. Removed entries have after: null; added entries have before: null. This JSON is the **actual output artifact**, not merely a console summary.

For a preview of the complete output without changing repository files:

    python -m json.tool output/report-day-02.json

### Repeatability and data integrity

Running the same source + snapshot again with equivalent parsed catalog content produces already_recorded: true and does **not** insert duplicates. Attempting to reuse the same snapshot name with different product records raises an error without overwriting stored history. Histories from different source identifiers are isolated. Invalid product IDs, duplicate IDs, missing titles, malformed prices and out-of-range amounts are rejected before database updates.

## Automated tests

    python -m unittest discover -s tests -v

The suite covers exact monetary parsing, HTML entities and whitespace, duplicates, missing/invalid fields, isolated histories, snapshot idempotence, revision conflicts, actual SQLite contents, changes in both directions, deterministic ordering, and CLI output/error handling.

## Limitations and production considerations

- This is an **offline HTML parsing demonstration**, not an operational scraper: it does not fetch URLs, render JavaScript, bypass anti-bot measures, follow pagination, schedule jobs, or integrate AI services.
- The HTML contract is intentionally narrow. Another website requires an authorized adapter and updated fixtures/tests. It is not safe to assume that every site can legally be collected.
- SQLite serializes writes; no multi-worker scheduling is implemented. Source and snapshot names must be short ASCII identifiers. Snapshot order follows the order in which new snapshots are inserted, not dates embedded in their names.
- The database commit and the output JSON file are separate steps. If disk writing fails afterward, database history may already be stored; rerunning with the same name safely regenerates the report.
- The output JSON is written with an atomic per-file replacement. Concurrency, backups, retention, HTTPS collection, access controls, production monitoring, and handling large datasets are beyond this demonstration.
