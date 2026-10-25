# Campaign Budget Pacing Audit

A Python 3.10+ command-line tool that checks fictional daily advertising
budgets and spending, and creates **two independently usable CSV reports**.
Uses only the Python standard library and intentionally avoids online APIs.

## Problem

Marketing teams receive daily spending reports from several campaigns.
They want to know which days exceeded the plan and whether each campaign
has exceeded its **cumulative allocated budget**. Duplicate exports may
repeat the same campaign/day, so they must not inflate totals.

Input CSV headers:

```text
campaign_id,date,budget_usd,spend_usd
```

The tool validates ISO dates and monetary values. Each budget must be positive;
a zero spend is allowed. Amounts use `decimal.Decimal` (never floats),
must have at most two cents, and are interpreted in USD without conversion.

For each campaign, daily rows are sorted by date before computing cumulative
spend and cumulative budget. A duplicate campaign/date is flagged and ignored
in the financial totals. Blank fields, invalid dates and amounts are flagged.

## Run and interpret

```sh
python3 pacing.py sample_daily_spend.csv issues.csv summary.csv
python3 -m unittest discover -s tests -v
```

**Issues CSV:** row number, campaign, date, issue code, explanation.

**Summary CSV:** campaign, number of valid unique dates, total planned budget,
total spend, budget remaining (negative = excess), and utilization percentage.

The sample identifies two daily overages and one duplicate campaign/day.
Exit codes are **0** for clean, **1** for detected issues, **2** for invalid
inputs or output failures.

This is a *budget audit*, not a forecast: it only accumulates dates present
in the input. It does not guess missing dates, contractual invoices, refunds,
timezone conversions, or attribution adjustments.

## Engineering details

Validation and aggregation are separated from CSV file handling and the CLI.
Budgeting uses integer-like decimal cents. Campaign grouping uses dictionary
lookups (average O(n)); per-campaign date sorting yields O(n log n) worst-case
time and O(n) additional memory.

## Next exercise

Allow a validated monthly target and report pacing versus elapsed calendar
days, including explicit handling for days without records.
