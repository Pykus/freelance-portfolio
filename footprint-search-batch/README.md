# Offline Search Footprint Batch and Deduplication

A reproducible Python 3 demonstration of batching search terms, consolidating
website results, rejecting invalid URLs, and exporting a clean CSV summary.
Designed as an independent portfolio demonstration for the kind of repetitive
search-API and spreadsheet work that businesses may need. **This is not client
work** and does not use client data. All examples and sites are fictional.

## What it solves

Given towns, phone area codes, postcode districts, and web design footprints,
the tool plans repeated searches, joins mock results from an offline fixture,
normalizes URLs and de-duplicates results before producing an audit report.

This demonstration intentionally uses a fixture instead of contacting PublicWWW,
scraping websites, or using credentials. Adapting the fixture interface to a
licensed search API would require that API's documented authentication, rate
limits, pagination, and terms of service.

## Requirements

Python 3.10 or newer; standard library only (no installation dependencies).

## Run the example

From this directory:

```bash
python3 footprint_batch.py \
  --locations examples/locations.csv \
  --footprints examples/footprints.txt \
  --fixture examples/mock-results.json \
  --output output
cat output/summary.json
cat output/sites.csv
```

Expected summary (order of JSON keys may vary):

```json
{
  "duplicate_hits": 1,
  "hits": 4,
  "invalid_urls": 1,
  "queries": 4,
  "unique_sites": 2
}
```

`output/sites.csv` contains the two unique fictional HTTPS site addresses,
their titles and the first matching town / footprint / term.

## Input format

- `locations.csv`: headers `town,area_code,postcodes`. Separate multiple
  postcodes using `|` inside the last field. Missing values are rejected.
- `footprints.txt`: one literal search footprint per line; `#` starts
  comment lines. Repeated footprints are ignored.
- `mock-results.json`: keys are `<footprint>|<term>`, values are lists of
  objects with string `url` and `title` fields. An absent key means zero hits.

The example creates four planned searches (one town, one area code, two
postcodes). The fixture returns four hits: two unique valid URLs, one
duplicate and one invalid scheme. Results are sorted deterministically.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q footprint_batch.py tests
```

Tests cover parsing, empty inputs, URL validation, repeated search terms,
normalization, deduplication, CSV formula protection, generated reports and
the complete example. Outputs are written to a chosen local directory.

## Design choices and limitations

A URL's scheme becomes HTTPS; `www.`, query strings, fragments and trailing
slashes are ignored for de-duplication. This is a **business rule** that may
merge distinct URLs; it should be reconsidered for other use cases.
Invalid URL hits are skipped and counted rather than terminating the batch.
CSV fields beginning with spreadsheet formula characters are quoted safely.
The fixture represents already-received results and does not measure search
coverage or perform live requests. This is a small demonstrator, not a
production crawler.
