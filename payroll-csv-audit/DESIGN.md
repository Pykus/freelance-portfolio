# Validation design

The auditor deliberately separates **observation** from **pay calculation**. It never adjusts amounts automatically. It preserves the source values in each flagged record, together with the issue codes explaining why a human review is necessary.

## Rules

- Employee IDs must be present and unique within a single CSV. The comparison ignores outer whitespace and case. All repeated occurrences are flagged.
- Store names must be present.
- Hour and money columns must hold finite, nonnegative Decimal values. Zero is accepted.
- Overtime exceeding a configurable limit (20 hours by default) is a review finding, not an automatic rejection of the record.
- Overtime cannot exceed reported worked hours.
- Values above 744 hours in the monthly hour columns are flagged as implausible. The 744-hour upper bound is deliberately generous; appropriate limits depend on the pay period.

The validator checks required header names and refuses empty or repeated headers. Unexpected extra data cells and missing cells are marked as malformed. A single row may contain several issue codes, and the summary counts findings by type as well as affected rows.

## Output safety

The CSV report quotes fields using Python's CSV writer and prefixes cells beginning with spreadsheet formula markers with an apostrophe. This is an output-only defense and does not mutate the input. Each report is written to a temporary sibling file, flushed, and then moved into place atomically. Together, the CSV and JSON are not a transactional pair.

## Extension points

A production workflow could validate per-location policy, support multiple currencies, process large streams with SQLite, and attach signed audit IDs. Those enhancements should be introduced only with clear business rules and regression tests.
