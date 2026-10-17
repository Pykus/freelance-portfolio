# Website migration redirect map audit

## The real problem

A small business is replacing its old website. Its developer has exported **six URLs** from the old site and prepared a spreadsheet mapping old URLs to new ones. Before launch, somebody must check the plan: every old page should redirect, redirects must not loop forever, and ideally a visitor should reach the new page in **one** hop.

**This command-line tool audits that proposed mapping without contacting any website.** It reads two simple CSV files and produces an actionable review list for the developer.

## What the example finds

The fictional migration from `old.example` to `new.example` contains:

| Old URL | Outcome | Why it matters |
| --- | --- | --- |
| /about, /contact | Direct | Good: one redirect to the new site |
| /pricing | Chain | Redirects to /plans on the old site, then to the new site |
| /blog | Loop | /blog → /news → /blog; visitors cannot reach a destination |
| /faq | Self-loop | Redirects back to itself |
| /terms | Missing | Old page has no redirect rule |

The extra rule for `/obsolete` also receives a warning because that URL is not in the inventory.

**Result:** 6 pages checked, 2 direct, 1 chained, 2 loops, 1 missing; 5 findings (including the unlisted rule). Intermediate redirect steps are not treated as unlisted sources.

## Run the example

Requires **Python 3.10 or later**; standard library only. From this directory:

```bash
python3 redirect_audit.py --output output
cat output/summary.json
cat output/audit.csv
cat output/findings.csv
```

`audit.csv` contains **one row per old URL** with its status, final destination (when reachable) and number of hops. `findings.csv` is a short developer to-do list, sorted by issue type. `summary.json` contains counts.

To use your own exports:

```bash
python3 redirect_audit.py --inventory old-urls.csv --redirects redirects.csv --output reports
```

The inventory file needs an `old_url` column. The mapping needs `source,target` columns. Every value should be an **absolute HTTP(S) URL**, not just a path. For CI scripts, add `--fail-on-errors` (exit code 1 for error findings, 2 for malformed input); by default the tool generates reports and exits 0.

## What gets checked

The tool reports incomplete coverage, loops, self-loops, chains requiring multiple hops, duplicate mappings, invalid URLs, repeated inventory rows and rules outside the inventory. It keeps the **first** redirect rule for a duplicated source and explicitly reports that conflict.

For accuracy, scheme, subdomains, paths, trailing slashes and query strings remain significant: `http://old.example/page` is not automatically identical to `https://old.example/page`. Hostnames are case-insensitive; URL fragments are ignored.

**Limitations:** This is a static audit of a CSV *plan*, not a live HTTP crawl or proof that a server has deployed redirects. It cannot detect server-side rules absent from the spreadsheet or confirm target pages exist. The example data and domains are fictional. Verify all results against staging before launching a real migration.

## Test

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q redirect_audit.py tests
```

The tests exercise direct/chain/cycle classification, coverage, duplicate handling, URL validity, exported reports, deterministic ordering and CLI exit codes.
