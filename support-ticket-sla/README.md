# First-response SLA audit for helpdesk ticket exports

## The real business problem

A managed IT helpdesk receives many customer tickets. Every ticket has a priority and a first-response deadline defined by a service-level agreement (SLA). At the end of the day, the manager needs to know:

- Which tickets received a timely first response?
- Which tickets were answered too late?
- Which unanswered tickets have **already missed** their deadline?
- Which tickets still have time left?
- Which closed tickets have **no response timestamp** and must be reviewed?

Manually calculating deadlines in a spreadsheet is error-prone, especially when export timestamps use different timezones.

## Example

Using a fictional helpdesk export of **6 tickets** at **2026-10-01 14:00 UTC**:

| Ticket | Priority, SLA | Outcome |
| --- | --- | --- |
| T-100 | Urgent, 1 hour | **met**: answered in 30 minutes |
| T-101 | High, 2 hours | **breached**: answered in 3 hours |
| T-102 | Normal, 8 hours | **pending**: not answered, deadline still ahead |
| T-103 | Urgent, 1 hour | **breached_open**: unanswered after 4 hours |
| T-104 | Normal, 8 hours | **met**: answered in 2 hours |
| T-105 | Low, 24 hours | **data_error**: closed without a first-response timestamp |

The program generates `ticket-sla.csv` for operational review and `summary.json` with **2 met, 1 breached, 1 breached_open, 1 pending, 1 data_error**. Three rows need human attention.

## Run it

Python 3.10+; **standard library only**. From this directory:

```bash
python3 sla_audit.py --output output
cat output/summary.json
cat output/ticket-sla.csv
```

Use your own CSV exports:

```bash
python3 sla_audit.py --tickets tickets.csv --policies policies.csv \
  --as-of 2026-10-01T14:00:00+00:00 --output reports
```

`tickets.csv` columns: `ticket_id,priority,state,opened_at,first_reply_at`. The reply timestamp may be **blank**, but the column is required. State must be `open` or `closed`. `policies.csv` columns: `priority,reply_within_hours`. Every priority requires a positive numeric limit.

All timestamps must be **ISO 8601 with a timezone**: `2026-10-01T15:00:00+01:00` or `2026-10-01T14:00:00Z`. The program converts all times to UTC before comparing deadlines. Duplicate IDs, unknown priorities and impossible event sequences produce an error rather than misleading reports.

## Business rules

- An answered ticket is **met** if the first reply is on or before the deadline; otherwise **breached**.
- An open ticket with no reply is **pending** if the report timestamp is on or before the deadline; otherwise **breached_open**.
- A closed ticket with no reply is **data_error**, because the export does not prove whether the SLA was met.
- **Response time** is wall-clock elapsed time, *not business or office hours*.

We do not assert that every closed ticket was solved successfully: this example audits first **responses**, not resolutions.

## Important limitations

The project processes local exports without accessing a helpdesk account. It does not calculate business-hour or holiday calendars, pause times, SLA exceptions, escalations, or time-to-resolution. Real SLAs may require those rules. The example tickets are synthetic and contain no personal data. Do not apply the elapsed-hours assumption to an actual contract without validating it first.

## Tests

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q sla_audit.py tests
```

Regression tests include exact response deadlines, unanswered and closed tickets, timezone conversion, bad input rejection, CSV safety and the end-to-end report.
