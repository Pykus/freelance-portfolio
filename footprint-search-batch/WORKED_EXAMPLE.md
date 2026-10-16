# Worked example: a one-person UK web studio preparing a research shortlist

## Imagine the job

You run a small website-maintenance business in Shrewsbury. You would like to research other local businesses whose sites **may** have been created using an older website-building service. Your goal is to find candidates for a **human review of their sites**, perhaps to understand the local market or explore whether website redesign services could be relevant.

You have noticed that some publicly visible website pages contain credits such as "Website by [supplier]" or include a recognisable source-code snippet. A source-code search engine such as PublicWWW can locate pages matching the snippet.

**The manual pain:** One clue multiplied by many towns, phone codes and postcodes creates dozens of searches. Search results contain repeated domains, different paths on one site, and stale or irrelevant results. Copying them into a spreadsheet takes time, and after you deduplicate you may lose the reason a website appeared.

This tool makes **that spreadsheet/organisation task** repeatable. It is not an automatic web searcher.

## Step 1 — Choose a small sample area

In examples/locations.csv:

~~~csv
town,area_code,postcodes
Shrewsbury,01743,SY1|SY2
~~~

In examples/footprints.txt:

~~~text
Website by Northstar Web Studio
Powered by Northstar Site Engine
~~~

**Northstar is fictitious**; it does not represent a real company. All .example websites in this story are invented. The town and phone code are real geographic terms but do not identify any real client.

## Step 2 — Prepare the searches

Run:

~~~bash
python3 footprint_batch.py --plan-only --output research-output
~~~

The tool calculates **2 provider clues × 4 location terms = 8 queries**.

For example:

~~~text
depth:all site:uk "Website by Northstar Web Studio" "Shrewsbury"
depth:all site:uk "Website by Northstar Web Studio" "01743"
depth:all site:uk "Website by Northstar Web Studio" "SY1"
depth:all site:uk "Website by Northstar Web Studio" "SY2"
depth:all site:uk "Powered by Northstar Site Engine" "Shrewsbury"
depth:all site:uk "Powered by Northstar Site Engine" "01743"
depth:all site:uk "Powered by Northstar Site Engine" "SY1"
depth:all site:uk "Powered by Northstar Site Engine" "SY2"
~~~

Those are **search instructions**, not search results. A researcher can paste them into an appropriate source-code search interface or use them to label manually exported results.

## Step 3 — You find seven observations, not seven businesses

Here is a shortened view of our imaginary results. The complete data is in examples/manual-search-results.csv.

| Search clue / place | Result |
| --- | --- |
| Website by Northstar / Shrewsbury | www.riverbank-bakery.example |
| Website by Northstar / Shrewsbury | flower-shop.example/offers |
| Website by Northstar / 01743 | riverbank-bakery.example/menu |
| Website by Northstar / 01743 | ftp://no-website.example/file (invalid) |
| Website by Northstar / SY1 | www.flower-shop.example/about |
| Powered by Northstar / 01743 | riverbank-bakery.example/contact |
| Powered by Northstar / SY2 | cobalt-dental.example/contact |

A person reading a raw export sees **seven rows** and might mistake repeated pages for different leads. In particular, **Riverbank Bakery appears three times**, including under two different supplier clues.

The example deliberately includes one invalid URL to demonstrate an honest error count.

## Step 4 — Import the results and keep the evidence

Run:

~~~bash
python3 footprint_batch.py --results-csv examples/manual-search-results.csv --output reviewed-output
~~~

Open reviewed-output/sites.csv, or [see the finished example file](examples/expected-sites.csv) online.

The cleaned output contains just three domain rows:

| Domain | Valid sightings | What you can tell a researcher |
| --- | ---: | --- |
| riverbank-bakery.example | 3 | Found using town + phone code and both supplier clues |
| flower-shop.example | 2 | Found using town + postcode and one supplier clue |
| cobalt-dental.example | 1 | Found using postcode and the second supplier clue |

Each full row also contains the **representative URL**, **title**, **all source-code clues**, **all location terms**, and **every search query** that produced the domain.

That distinction matters: the worker can open the candidate sites once, see the reasons for inclusion, and verify them. They do not need to reconstruct the search history from separate spreadsheets.

## Step 5 — Decide what to do with the list

This is a **research shortlist**, not a list of verified customers of any supplier:

1. Open each candidate's current website.
2. Check whether the footer/source-code clue is really there today.
3. Verify that the business is actually in the intended area.
4. Mark genuine matches in your own research spreadsheet and ignore false positives.

No personal contact data is extracted, and the program does not send messages.

## What makes this a realistic portfolio problem?

Public freelance briefs explicitly ask developers to combine **website source-code footprints**, **towns / phone codes / postcodes**, **deduplication**, and **traceable search history** in a CSV lead list:

- [UK business website discovery using PublicWWW](https://www.upwork.com/freelance-jobs/apply/Build-Python-Tool-Identify-Business-Websites-Using-PublicWWW-API_~022110038686775173021/)
- [Batch PublicWWW searches and export CSV](https://www.upwork.com/freelance-jobs/apply/Build-Simple-PublicWWW-Lead-Scraping-Tool-Automation-Export-Website-Results-CSV_~022107790691124070689/)

The briefs additionally request **automated API searches**, and sometimes live verification. **Those capabilities are not present here.** The portfolio project deliberately demonstrates only a free-to-run, offline piece of that workflow: planning, copying/importing results, deduplication, and explaining the audit trail.

A production implementation would need a properly authorized data source, authentication, rate-limit handling, pagination, retry/resume logic, site verification and a friendly one-click interface.
