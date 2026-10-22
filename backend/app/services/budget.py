"""Planning entries, periods, recurrence and period summaries.

Month-end rule for monthly recurrence: an entry recurs on the day of month of its
start date; in months without that day it falls on the month's last day
(e.g. 31 Jan -> 28/29 Feb -> 31 Mar). The anchor day never drifts.
"""

from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ..errors import DomainError, not_found
from ..money import parse_amount, to_string, validate_currency
from .common import iso, log_event, new_id, parse_date, require_not_future
from .ledger import INCOME_KINDS, SPENDING_KINDS, get_account_row, list_transactions, post
from .rates import Rate, UnsupportedPair, convert, get_rate

MAX_PERIOD_DAYS = 366


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # inclusive
    kind: str  # month | custom

    def as_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "kind": self.kind}


def month_period(month: str) -> Period:
    try:
        year, mon = (int(p) for p in month.split("-"))
        start = date(year, mon, 1)
    except (ValueError, TypeError) as exc:
        raise DomainError(422, "invalid_period", "Month must look like 2026-10.") from exc
    return Period(start, date(year, mon, calendar.monthrange(year, mon)[1]), "month")


def resolve_period(month: str | None, start: str | None, end: str | None, today: date) -> Period:
    if start or end:
        if not (start and end):
            raise DomainError(422, "invalid_period", "A custom range needs both a start and an end date.")
        s, e = parse_date(start, "start"), parse_date(end, "end")
        if e < s:
            raise DomainError(422, "invalid_period", "The end date must be on or after the start date.")
        if (e - s).days + 1 > MAX_PERIOD_DAYS:
            raise DomainError(422, "invalid_period", f"Custom ranges can cover at most {MAX_PERIOD_DAYS} days.")
        return Period(s, e, "custom")
    return month_period(month or f"{today.year:04d}-{today.month:02d}")


def _add_months(anchor: date, months: int) -> date:
    total = anchor.month - 1 + months
    year, month = anchor.year + total // 12, total % 12 + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def occurrences(entry: dict[str, str | None], start: date, end: date) -> list[date]:
    first = date.fromisoformat(str(entry["start_date"]))
    last = date.fromisoformat(str(entry["end_date"])) if entry.get("end_date") else None
    if entry["recurrence"] == "none":
        return [first] if start <= first <= end and (last is None or first <= last) else []
    result: list[date] = []
    # Jump close to the range start instead of iterating from the anchor.
    months = max(0, (start.year - first.year) * 12 + start.month - first.month - 1)
    while True:
        day = _add_months(first, months)
        months += 1
        if day > end or (last is not None and day > last):
            break
        if day >= start:
            result.append(day)
    return result


# --- entries -------------------------------------------------------------------


def _entry(row: sqlite3.Row) -> dict[str, str | None]:
    return {k: row[k] for k in ("id", "kind", "category", "description", "amount", "currency", "start_date", "recurrence", "end_date")}


def list_entries(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, str | None]]:
    rows = conn.execute(
        "SELECT * FROM budget_entries WHERE workspace_id = ? ORDER BY start_date, created_at, rowid", (workspace_id,)
    ).fetchall()
    return [_entry(r) for r in rows]


def get_entry(conn: sqlite3.Connection, workspace_id: str, entry_id: str) -> dict[str, str | None]:
    row = conn.execute("SELECT * FROM budget_entries WHERE workspace_id = ? AND id = ?", (workspace_id, entry_id)).fetchone()
    if row is None:
        raise not_found("Budget entry")
    return _entry(row)


def create_entry(
    conn: sqlite3.Connection,
    workspace_id: str,
    *,
    kind: str,
    category: str,
    description: str,
    amount: str,
    currency: str,
    start_date: str,
    recurrence: str,
    end_date: str | None,
    now: datetime,
) -> dict[str, str | None]:
    validate_currency(currency)
    value = parse_amount(amount, currency)
    if value <= 0:
        raise DomainError(422, "invalid_amount", "Amounts must be greater than zero.")
    first = parse_date(start_date, "start_date")
    if end_date is not None and parse_date(end_date, "end_date") < first:
        raise DomainError(422, "invalid_period", "The end date must be on or after the start date.")
    entry_id = new_id("bud")
    conn.execute(
        "INSERT INTO budget_entries (id, workspace_id, kind, category, description, amount, currency, start_date,"
        " recurrence, end_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entry_id, workspace_id, kind, category, description, to_string(value, currency), currency,
         first.isoformat(), recurrence, end_date, iso(now)),
    )
    log_event(conn, workspace_id, now, "budget_entry_created", "budget_entry", entry_id, kind=kind, amount=to_string(value, currency), currency=currency)
    return get_entry(conn, workspace_id, entry_id)


def record_occurrence(
    conn: sqlite3.Connection,
    workspace_id: str,
    entry_id: str,
    occurrence_date: date,
    account_id: str,
    occurred_on: date,
    today: date,
    now: datetime,
) -> str:
    """Record one planned occurrence as paid (expense) or received (income): post the actual
    transaction and link it, in the caller's transaction. Only this explicit action links a
    plan to an actual; transactions entered separately are never matched automatically."""
    entry = get_entry(conn, workspace_id, entry_id)
    if occurrences(entry, occurrence_date, occurrence_date) != [occurrence_date]:
        raise DomainError(422, "not_an_occurrence", "This plan has no occurrence on that date.")
    account = get_account_row(conn, workspace_id, account_id)
    if account["currency"] != entry["currency"]:
        raise DomainError(422, "currency_mismatch", "Choose an account in the same currency as the planned entry.")
    require_not_future(occurred_on, today, "occurred_on")
    existing = conn.execute(
        "SELECT transaction_id FROM plan_fulfilments WHERE workspace_id = ? AND entry_id = ? AND occurrence_date = ?",
        (workspace_id, entry_id, occurrence_date.isoformat()),
    ).fetchone()
    if existing is not None:
        raise DomainError(409, "already_recorded", "This planned occurrence is already recorded.",
                          transaction_id=existing["transaction_id"])
    transaction_id = post(
        conn, workspace_id, account_id, str(entry["kind"]), Decimal(str(entry["amount"])), str(entry["category"]),
        str(entry["description"]), occurred_on, now,
        source_type="plan_occurrence", source_id=f"{entry_id}@{occurrence_date.isoformat()}",
    )
    conn.execute(
        "INSERT INTO plan_fulfilments (workspace_id, entry_id, occurrence_date, transaction_id, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (workspace_id, entry_id, occurrence_date.isoformat(), transaction_id, iso(now)),
    )
    log_event(conn, workspace_id, now, "plan_occurrence_recorded", "budget_entry", entry_id,
              occurrence_date=occurrence_date.isoformat(), amount=entry["amount"], currency=entry["currency"],
              transaction_id=transaction_id)
    return transaction_id


def delete_entry(conn: sqlite3.Connection, workspace_id: str, entry_id: str, now: datetime) -> None:
    get_entry(conn, workspace_id, entry_id)
    conn.execute("DELETE FROM budget_entries WHERE workspace_id = ? AND id = ?", (workspace_id, entry_id))
    log_event(conn, workspace_id, now, "budget_entry_deleted", "budget_entry", entry_id)


# --- conversion to the display currency ------------------------------------------


class Valuer:
    """Converts originals to the display currency using the latest snapshot per pair
    at the time of viewing. Originals are never changed; missing pairs are reported."""

    def __init__(self, conn: sqlite3.Connection, workspace_id: str, display_currency: str) -> None:
        self.conn = conn
        self.workspace_id = workspace_id
        self.display = display_currency
        self._rates: dict[str, Rate | None] = {}

    def rate(self, currency: str) -> Rate | None:
        if currency not in self._rates:
            try:
                self._rates[currency] = get_rate(self.conn, self.workspace_id, currency, self.display)
            except UnsupportedPair:
                self._rates[currency] = None
        return self._rates[currency]

    def value(self, amount: Decimal, currency: str) -> Decimal | None:
        rate = self.rate(currency)
        return None if rate is None else convert(amount, rate)

    def rates_used(self) -> list[dict[str, object]]:
        return [r.as_dict() for r in self._rates.values() if r is not None and r.mode != "identity"]

    def missing(self) -> list[str]:
        return sorted(c for c, r in self._rates.items() if r is None)

    def policy(self) -> dict[str, object]:
        return {
            "display_currency": self.display,
            "method": "latest_snapshot_at_view_time",
            "rates": self.rates_used(),
            "missing_pairs": [f"{c}->{self.display}" for c in self.missing()],
        }


def _item(valuer: Valuer, amount: Decimal, currency: str) -> dict[str, str | None]:
    converted = valuer.value(amount, currency)
    return {
        "amount": to_string(amount, currency),
        "currency": currency,
        "display_amount": None if converted is None else to_string(converted, valuer.display),
    }


def fulfilled_occurrences(conn: sqlite3.Connection, workspace_id: str) -> dict[tuple[str, str], str]:
    """(entry_id, occurrence_date) -> transaction_id for occurrences explicitly recorded as paid/received."""
    rows = conn.execute(
        "SELECT entry_id, occurrence_date, transaction_id FROM plan_fulfilments WHERE workspace_id = ?", (workspace_id,)
    ).fetchall()
    return {(r["entry_id"], r["occurrence_date"]): r["transaction_id"] for r in rows}


def planned_items(conn: sqlite3.Connection, workspace_id: str, start: date, end: date, valuer: Valuer) -> list[dict[str, object]]:
    """Every planned occurrence in the range (the plan is never changed). Occurrences that were
    explicitly recorded as paid/received carry fulfilled=True and their transaction id."""
    items: list[dict[str, object]] = []
    fulfilled = fulfilled_occurrences(conn, workspace_id)
    for entry in list_entries(conn, workspace_id):
        for day in occurrences(entry, start, end):
            link = fulfilled.get((str(entry["id"]), day.isoformat()))
            items.append(
                {
                    "entry_id": entry["id"],
                    "date": day.isoformat(),
                    "fulfilled": link is not None,
                    "transaction_id": link,
                    "kind": entry["kind"],
                    "category": entry["category"],
                    "description": entry["description"],
                    "recurrence": entry["recurrence"],
                    **_item(valuer, Decimal(str(entry["amount"])), str(entry["currency"])),
                }
            )
    items.sort(key=lambda i: (str(i["date"]), str(i["kind"])))
    return items


def summary(conn: sqlite3.Connection, workspace_id: str, period: Period, display_currency: str) -> dict[str, object]:
    """Planned vs actual for one period, valued in the display currency."""
    valuer = Valuer(conn, workspace_id, display_currency)
    planned = planned_items(conn, workspace_id, period.start, period.end, valuer)
    actual_rows = list_transactions(conn, workspace_id, period.start, period.end)

    zero = Decimal(0)
    totals = {"planned_income": zero, "planned_expenses": zero, "actual_income": zero, "actual_expenses": zero}
    categories: dict[str, dict[str, Decimal]] = {}
    unconverted = 0

    def add(kind_key: str, category: str, column: str, display_amount: str | None) -> None:
        nonlocal unconverted
        if display_amount is None:
            unconverted += 1
            return
        value = Decimal(display_amount)
        totals[kind_key] += value
        if kind_key.endswith("expenses"):
            categories.setdefault(category, {"planned": zero, "actual": zero})[column] += value

    for item in planned:
        key = "planned_income" if item["kind"] == "income" else "planned_expenses"
        add(key, str(item["category"]), "planned", item["display_amount"])  # type: ignore[arg-type]

    actual: list[dict[str, object]] = []
    for row in actual_rows:
        item = {**row, **_item(valuer, Decimal(str(row["amount"])), str(row["currency"]))}
        actual.append(item)
        if row["kind"] in INCOME_KINDS:
            add("actual_income", str(row["category"]), "actual", item["display_amount"])  # type: ignore[arg-type]
        elif row["kind"] in SPENDING_KINDS:
            add("actual_expenses", str(row["category"]), "actual", item["display_amount"])  # type: ignore[arg-type]

    d = display_currency
    return {
        "period": period.as_dict(),
        "display_currency": d,
        "planned_income": to_string(totals["planned_income"], d),
        "planned_expenses": to_string(totals["planned_expenses"], d),
        "planned_remainder": to_string(totals["planned_income"] - totals["planned_expenses"], d),
        "actual_income": to_string(totals["actual_income"], d),
        "actual_expenses": to_string(totals["actual_expenses"], d),
        "actual_net": to_string(totals["actual_income"] - totals["actual_expenses"], d),
        "categories": [
            {"category": c, "planned": to_string(v["planned"], d), "actual": to_string(v["actual"], d),
             "difference": to_string(v["planned"] - v["actual"], d)}
            for c, v in sorted(categories.items())
        ],
        "planned_items": planned,
        "actual_items": actual,
        "unconverted_count": unconverted,
        "complete": unconverted == 0,
        "valuation": valuer.policy(),
    }

