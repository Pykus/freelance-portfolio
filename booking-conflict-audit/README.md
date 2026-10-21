# Booking Conflict Auditor

An offline Python 3.11+ utility that checks fictional booking exports for duplicate identifiers, invalid timestamps and double-booked resources. It reports all overlapping active reservations, never overwrites the input, and needs only the standard library.

## Use

Save bookings to CSV with these required columns: booking_id, resource_id, start_at, end_at, status. Dates must be ISO-8601 with a numeric UTC offset or Z. Status may be scheduled, confirmed, or cancelled.

Run from this project directory:

    python3 -m booking_audit path/to/bookings.csv --conflicts conflicts.csv --issues issues.csv --summary summary.json
    python3 -m unittest discover -s tests -v

Output includes a conflict CSV (two booking identifiers, resource, UTC overlap window and integer overlap duration), an input-quality issue CSV, and a summary JSON. All identifiers in CSV reports are escaped when they look like spreadsheet formulas.

## Behavior

The auditor compares half-open intervals [start, end), so back-to-back reservations are allowed. It compares timestamps in UTC, accepts case-insensitive resource identifiers, ignores cancelled reservations, and excludes invalid records from overlap matching. Duplicated booking IDs are flagged in **all** affected input rows. Nested overlaps produce every conflicting pair.

Intervals are grouped by resource and sorted by UTC start time. An active min-heap evicts elapsed intervals; the remaining active set produces each overlapping pair. Complexity is O(n log n + k), where k is the number of overlapping pairs to report. Extreme shared-resource conflicts can legitimately produce quadratic output.

## Limitations

This is a diagnostic tool, not an online booking transaction service or an authorization mechanism. It does not process recurrence rules, holidays, staff availability or regional timezone names. Invalid timezone-naive inputs are rejected rather than guessed. Additional CSV columns are accepted, but missing/repeated required headers are an error.

Output files are individually replaced atomically, **not** as one multi-file transaction. Keep generated files together for the same audit run. This repository uses synthetic examples and no confidential information.
