"""Evaluate first-response SLAs from exported helpdesk tickets and policy CSVs.

Measures elapsed real-world hours (not business hours) with timezone-aware times.
No external service, API, database, or network access is required.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUTPUT_FIELDS = ("ticket_id", "priority", "state", "opened_at",
                 "first_reply_at", "deadline", "elapsed_hours",
                 "allowed_hours", "result")


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Timezone offset required: {value!r}")
    return parsed.astimezone(timezone.utc)


def read_rows(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError(f"{path.name} requires columns: {', '.join(required)}")
        rows = []
        for line, row in enumerate(reader, 2):
            if any(not (row.get(field) or "").strip() for field in required
                   if field != "first_reply_at"):
                raise ValueError(f"{path.name} is missing a value at line {line}")
            rows.append({key: (value or "").strip()
                         for key, value in row.items() if key is not None})
    if not rows:
        raise ValueError(f"{path.name} contains no records")
    return rows


def read_policies(path: Path) -> dict[str, float]:
    rows = read_rows(path, ("priority", "reply_within_hours"))
    policies: dict[str, float] = {}
    for row in rows:
        name = row["priority"]
        try:
            hours = float(row["reply_within_hours"])
        except ValueError as exc:
            raise ValueError(f"Non-numeric SLA for {name!r}") from exc
        if name in policies or not math.isfinite(hours) or hours <= 0.0:
            raise ValueError(f"Duplicate or invalid policy: {name!r}")
        policies[name] = hours
    return policies


def audit(tickets: list[dict[str, str]], policies: dict[str, float],
          as_of: datetime) -> tuple[list[dict[str, str]], dict[str, int]]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)
    ids: set[str] = set()
    output = []
    counts: Counter[str] = Counter()

    for row in tickets:
        ticket_id = row["ticket_id"]
        priority = row["priority"]
        state = row["state"].lower()
        if ticket_id in ids:
            raise ValueError(f"Duplicate ticket ID {ticket_id!r}")
        ids.add(ticket_id)
        if priority not in policies:
            raise ValueError(f"No SLA policy for priority {priority!r}")
        if state not in ("open", "closed"):
            raise ValueError(f"Unexpected state for {ticket_id!r}: {state!r}")

        opened = parse_timestamp(row["opened_at"])
        if opened > as_of:
            raise ValueError(f"Ticket opened after report date: {ticket_id}")
        raw_reply = row.get("first_reply_at", "")
        reply = parse_timestamp(raw_reply) if raw_reply else None
        if reply is not None and (reply < opened or reply > as_of):
            raise ValueError(f"Response outside reporting period: {ticket_id}")

        hours_allowed = policies[priority]
        deadline = opened + timedelta(hours=hours_allowed)
        elapsed = ((reply or as_of) - opened).total_seconds() / 3600.0
        if reply is not None:
            result = "met" if reply <= deadline else "breached"
        elif state == "closed":
            result = "data_error"
        else:
            result = "pending" if as_of <= deadline else "breached_open"

        counts[result] += 1
        output.append({
            "ticket_id": ticket_id, "priority": priority, "state": state,
            "opened_at": opened.isoformat(), "first_reply_at":
                reply.isoformat() if reply else "",
            "deadline": deadline.isoformat(), "elapsed_hours": f"{elapsed:.2f}",
            "allowed_hours": f"{hours_allowed:g}", "result": result,
        })

    output.sort(key=lambda row: row["ticket_id"])
    summary = {"total_tickets": len(output)}
    for status in ("met", "breached", "breached_open", "pending", "data_error"):
        summary[status] = counts[status]
    summary["needs_attention"] = sum(
        summary[s] for s in ("breached", "breached_open", "data_error"))
    return output, summary


def safe_cell(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def write_report(rows: list[dict[str, str]], summary: dict[str, int],
                 output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "ticket-sla.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows({name: safe_cell(row[name]) for name in OUTPUT_FIELDS}
                         for row in rows)
    (output / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    examples = Path(__file__).resolve().parent / "examples"
    parser = argparse.ArgumentParser(
        description="Audit timezone-aware, elapsed-hour first-response SLAs")
    parser.add_argument("--tickets", type=Path, default=examples / "tickets.csv")
    parser.add_argument("--policies", type=Path, default=examples / "slas.csv")
    parser.add_argument("--as-of", default="2026-10-01T14:00:00+00:00",
                        help="ISO 8601 report timestamp with timezone")
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args(argv)
    try:
        policies = read_policies(args.policies)
        tickets = read_rows(args.tickets,
                            ("ticket_id", "priority", "state", "opened_at",
                             "first_reply_at"))
        rows, summary = audit(tickets, policies, parse_timestamp(args.as_of))
        write_report(rows, summary, args.output)
    except (OSError, ValueError, OverflowError, csv.Error) as exc:
        parser.exit(2, f"Input error: {exc}\n")
    print(json.dumps(summary, sort_keys=True))
    print(f"Reports: {args.output / 'ticket-sla.csv'}, {args.output / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
