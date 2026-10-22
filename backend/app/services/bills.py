"""Manual tuition and campus bills. Editing a bill bumps its version and invalidates
any proposal prepared for the previous terms."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ..errors import DomainError, not_found
from ..money import parse_amount, to_string, validate_currency
from .common import iso, log_event, new_id, parse_date

BILL_FIELDS = ("id", "description", "payee", "category", "amount", "currency", "due_date", "status", "version",
               "settled_on", "settled_by_execution_id")


def _bill(row: sqlite3.Row) -> dict[str, object]:
    return {k: row[k] for k in BILL_FIELDS}


def list_bills(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT * FROM bills WHERE workspace_id = ? ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, due_date, rowid",
        (workspace_id,),
    ).fetchall()
    return [_bill(r) for r in rows]


def get_bill(conn: sqlite3.Connection, workspace_id: str, bill_id: str) -> dict[str, object]:
    row = conn.execute("SELECT * FROM bills WHERE workspace_id = ? AND id = ?", (workspace_id, bill_id)).fetchone()
    if row is None:
        raise not_found("Bill")
    return _bill(row)


def _validated(amount: str, currency: str, due_date: str) -> tuple[str, str]:
    validate_currency(currency)
    value = parse_amount(amount, currency)
    if value <= 0:
        raise DomainError(422, "invalid_amount", "Amounts must be greater than zero.")
    return to_string(value, currency), parse_date(due_date, "due_date").isoformat()


def create_bill(conn: sqlite3.Connection, workspace_id: str, *, description: str, payee: str, category: str,
                amount: str, currency: str, due_date: str, now: datetime) -> dict[str, object]:
    amount_s, due_s = _validated(amount, currency, due_date)
    bill_id = new_id("bill")
    conn.execute(
        "INSERT INTO bills (id, workspace_id, description, payee, category, amount, currency, due_date, status, version,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', 1, ?, ?)",
        (bill_id, workspace_id, description, payee, category, amount_s, currency, due_s, iso(now), iso(now)),
    )
    log_event(conn, workspace_id, now, "bill_created", "bill", bill_id, amount=amount_s, currency=currency, due_date=due_s)
    return get_bill(conn, workspace_id, bill_id)


def update_bill(conn: sqlite3.Connection, workspace_id: str, bill_id: str, *, description: str, payee: str, category: str,
                amount: str, currency: str, due_date: str, now: datetime) -> dict[str, object]:
    bill = get_bill(conn, workspace_id, bill_id)
    if bill["status"] != "open":
        raise DomainError(409, "invalid_state", "Only open bills can be changed.")
    amount_s, due_s = _validated(amount, currency, due_date)
    conn.execute(
        "UPDATE bills SET description = ?, payee = ?, category = ?, amount = ?, currency = ?, due_date = ?,"
        " version = version + 1, updated_at = ? WHERE workspace_id = ? AND id = ?",
        (description, payee, category, amount_s, currency, due_s, iso(now), workspace_id, bill_id),
    )
    # Proposals prepared for the old terms need a fresh review.
    invalidated = conn.execute(
        "UPDATE payment_proposals SET status = 'cancelled', status_reason = 'bill_changed', updated_at = ?"
        " WHERE workspace_id = ? AND bill_id = ? AND status IN ('draft', 'ready_for_review', 'approved')",
        (iso(now), workspace_id, bill_id),
    ).rowcount
    log_event(conn, workspace_id, now, "bill_updated", "bill", bill_id, amount=amount_s, currency=currency,
              due_date=due_s, invalidated_proposals=invalidated)
    return get_bill(conn, workspace_id, bill_id)
