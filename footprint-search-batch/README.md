# Find business websites by who built them — a practical research assistant

**The business problem:** A small UK web-design agency wants to identify local businesses whose websites appear to use a particular website supplier. Finding these businesses manually is slow: the researcher searches for footer text such as "Website by Northstar Web Studio", combines it with a town or postcode, and keeps encountering the **same business in several searches**.

**What this program does:** It prepares copy/paste-ready searches, accepts results collected by a human, and turns messy repeated matches into a **CSV shortlist of distinct websites**. For every website, it records **which phrase and location term found it**.

**What it does NOT do:** It does not perform live web searches, scrape websites, identify email addresses, contact businesses, or prove that a supplier built a website. The example company, businesses and domains are imaginary. No account, API key, subscription or extra library is needed for the demonstration.

## The example in plain English

Imagine you are researching businesses around **Shrewsbury, UK**.

- The supplier may have left a website credit: **Website by Northstar Web Studio**.
- Or another piece of source code may say: **Powered by Northstar Site Engine**.
- You want to search for each clue alongside **Shrewsbury**, its phone area code **01743**, and postcode districts **SY1** and **SY2**.

Two clues multiplied by four location terms gives **8 searches**, including:

~~~text
depth:all site:uk "Website by Northstar Web Studio" "Shrewsbury"
depth:all site:uk "Website by Northstar Web Studio" "01743"
depth:all site:uk "Powered by Northstar Site Engine" "SY2"
~~~

Suppose the results include a bakery at **www.riverbank-bakery.example**, then the same bakery again at **riverbank-bakery.example/menu**, and once more at **riverbank-bakery.example/contact** under the second clue. A spreadsheet might count these as three leads. The program correctly counts **one domain with three supporting search matches**.

### What you get

The included worked example starts with **8 planned searches**, receives **7 fictional result rows**, rejects **1 invalid URL**, combines **3 repeated hits**, and produces **3 website records**:

| Business website (fictional) | Search matches | Why it appeared |
| --- | ---: | --- |
| riverbank-bakery.example | 3 | Shrewsbury / 01743; both website-supplier clues |
| flower-shop.example | 2 | Shrewsbury / SY1; website credit |
| cobalt-dental.example | 1 | SY2; supplier platform text |

The detailed file includes the actual search queries behind each row.

**[Open the complete example shortlist](examples/expected-sites.csv)** — readable directly on GitHub, without installing anything.

For a step-by-step story of how a freelancer would use it, read **[WORKED_EXAMPLE.md](WORKED_EXAMPLE.md)**.

## Try it in 30 seconds

Requires **Python 3.10+** and no external packages. In this directory:

~~~bash
python3 footprint_batch.py --demo --output demo-output
~~~

Open:

- **demo-output/sites.csv** — one row per distinct business domain, with all matching clues, locations and queries.
- **demo-output/queries.csv** — eight generated searches suitable for copying into the PublicWWW search interface.
- **demo-output/summary.json** — counts showing how many results were found, rejected or combined.

Example summary:

~~~json
{
  "queries": 8,
  "hits": 7,
  "unique_sites": 3,
  "duplicate_hits": 3,
  "invalid_urls": 1
}
~~~

All results in this demo are fictional and supplied in the repository. No network requests are made.

## Use it for your own research, without editing Python

1. Edit **examples/locations.csv** in a spreadsheet. Its columns are **town**, **area_code**, **postcodes**. Separate multiple postcode districts using a vertical bar, e.g. **SY1|SY2**.
2. Edit **examples/footprints.txt**. Add one website-code clue per line, ideally based on a publicly visible footer or an identifiable source fragment.
3. Generate the search plan:

~~~bash
python3 footprint_batch.py --plan-only --output research-output
~~~

4. Open **research-output/queries.csv**. Copy the **query** text into [PublicWWW](https://publicwww.com/) or another search service that understands the same query syntax. Check that searching is permitted and respect its terms and limits.
5. As you research, create a CSV file with the columns **query,url,title**. Copy the **exact** query from queries.csv into each result row, then record the returned website URL and an optional title. Each search result takes one row; you do not have to remove duplicates by hand. Use **[examples/manual-search-results.csv](examples/manual-search-results.csv)** as a working template.
6. Process the collected results:

~~~bash
python3 footprint_batch.py --results-csv examples/manual-search-results.csv --output reviewed-output
~~~

Replace the sample CSV path above with your own file when ready. Then open **reviewed-output/sites.csv**. The program combines matches from different searches by **website hostname**, removes duplicates and preserves the search evidence.

**Important:** The example CSV is an offline imitation of manually collected search results. The program does **not** automatically connect to PublicWWW or collect data for you.

## How this maps to a real freelance request

Public Upwork project descriptions ask for tools that find UK websites from supplier-specific source-code clues and location terms, then return a deduplicated, auditable list of domains. Examples:

- [Build a Python Tool to Identify UK Business Websites Using PublicWWW API](https://www.upwork.com/freelance-jobs/apply/Build-Python-Tool-Identify-Business-Websites-Using-PublicWWW-API_~022110038686775173021/)
- [Build a Simple PublicWWW Lead-Scraping Tool / Automation to Export Website Results to CSV](https://www.upwork.com/freelance-jobs/apply/Build-Simple-PublicWWW-Lead-Scraping-Tool-Automation-Export-Website-Results-CSV_~022107790691124070689/)

These requests inspired the **problem category**, not the fictional sample data. Their full scope includes **automated PublicWWW API requests**, error handling and sometimes live verification. **This repository implements only the query-planning and results-cleaning portion**, with a manual CSV import; it is **not** a complete implementation of either job.

This smaller version still solves a practical subtask: prepare searches consistently, turn copied results into a reviewable lead list, and preserve the evidence for a human researcher.

## How to judge a result

A search hit is **a candidate, not a confirmed client or provider relationship**. Before contacting or reporting a business, inspect its live website, check whether the clue is still present, and verify that the business actually operates in the area. Keep research and outreach compliant with applicable rules.

**Deduplication rules:** HTTP and HTTPS, a leading "www.", query strings, fragments and different paths count as the same hostname. Other subdomains remain separate (shop.example.com versus example.com). This can merge pages intentionally; the output retains one representative matching URL. It does **not** combine two different domains belonging to one company.

Invalid URLs are skipped and counted. Search results copied with a query absent from the generated plan cause a clear error rather than being assigned to the wrong town. Spreadsheet formula-like values are protected in the exported CSV.

## Run tests

~~~bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q footprint_batch.py tests
~~~

The tests cover example-to-output calculations, domain-level deduplication, preserving multiple search clues, CSV imports, query generation, invalid URLs, input errors, and spreadsheet-safe exports.

## Files at a glance

| File | Purpose |
| --- | --- |
| footprint_batch.py | Search planner, importer, deduplication and CSV reporting |
| examples/locations.csv | Fictional research area; easy to edit in Excel |
| examples/footprints.txt | Fictional source-code clues |
| examples/mock-results.json | Offline search-result fixture used in the demo |
| examples/manual-search-results.csv | Same observations in a format a person can fill out |
| examples/expected-sites.csv | Final shortlist, visible on GitHub without running code |
| WORKED_EXAMPLE.md | Business story and an annotated result |
| tests/test_footprint_batch.py | Automated checks |

No paid API is required to use the offline demonstration or process manually collected results.
