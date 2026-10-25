# Batch Job Run Reconciliation

An offline Python 3.10+ auditor for comparing an **expected set of scheduled
jobs** with an **observed execution log**. It catches missing, late, failed,
cancelled, duplicate and unexpected runs without making any network calls.

## The problem

A list of tasks that *should* have run is not proof that they actually
ran. A reliable operational report must join planned slots to observed
execution results. This demo accepts two synthetic CSV exports:

```text
plan.csv: slot_id,scheduled_at
runs.csv: slot_id,started_at,status
```

Timestamps must be ISO 8601 values **with explicit UTC offsets**.
The auditor compares actual instants, not just wall-clock strings, so
`10:05+02:00` and `08:05+00:00` represent the same time.

The default permitted start delay is 15 minutes. Successful on-time
runs are omitted from the issue CSV; missing or failed runs produce
issues. Duplicate IDs are also flagged. A late failed run produces
both observations so neither fact disappears.

## Run

```sh
python3 audit.py sample_plan.csv sample_runs.csv issues.csv
python3 -m unittest discover -s tests -v
```

Sample expected findings: one late start, one failed run, one missing run.
Exit statuses: **0** no issues, **1** issues found, **2** invalid input.
The report format is `slot_id,code,detail`.

## Engineering details

`audit_rows` uses deterministic dictionaries to match planned and
observed events in average O(n) time and O(n) space. The file layer
only handles CSV; tests exercise time-zone offsets, boundary delays,
duplicate IDs, missing runs and malformed records.

**Limitations:** this is not a scheduler, log collector, task launcher
or monitoring service. The user must provide authentic source logs.
The tool cannot deduce why a missing execution failed to run.

## Extension exercise

Support multiple attempts for one job, while distinguishing first-run
start time from final retry success and retaining an audit trail.
