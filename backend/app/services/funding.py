"""Contributions, savings goals and the reserve policy."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from ..errors import DomainError, not_found
from ..money import parse_amount, to_string
from .common import iso, log_event, new_id, parse_date
from .ledger import balance, get_account_row, post

# --- contributions ---------------------------------------------------------------


def _contribution(row: sqlite3.Row) -> dict[str, str | None]:
    return {k: row[k] for k in ("id", "account_id", "contributor", "amount", "currency", "expected_date", "certainty", "status", "received_on")}


def list_contributions(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, str | None]]:
    rows = conn.execute(
        "SELECT * FROM contributions WHERE workspace_id = ? ORDER BY expected_date, created_at, rowid", (workspace_id,)
    ).fetchall()
    return [_contribution(r) for r in rows]


def get_contribution(conn: sqlite3.Connection, workspace_id: str, contribution_id: str) -> dict[str, str | None]:
    row = conn.execute(
        "SELECT * FROM contributions WHERE workspace_id = ? AND id = ?", (workspace_id, contribution_id)
    ).fetchone()
    if row is None:
        raise not_found("Contribution")
    return _contribution(row)


def create_contribution(
    conn: sqlite3.Connection,
    workspace_id: str,
    *,
    account_id: str,
    contributor: str,
    amount: str,
    expected_date: str,
    certainty: str,
    now: datetime,
) -> dict[str, str | None]:
    account = get_account_row(conn, workspace_id, account_id)
    currency = account["currency"]
    value = parse_amount(amount, currency)
    if value <= 0:
        raise DomainError(422, "invalid_amount", "Amounts must be greater than zero.")
    expected = parse_date(expected_date, "expected_date")
    contribution_id = new_id("ctb")
    conn.execute(
        "INSERT INTO contributions (id, workspace_id, account_id, contributor, amount, currency, expected_date,"
        " certainty, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'expected', ?)",
        (contribution_id, workspace_id, account_id, contributor, to_string(value, currency), currency,
         expected.isoformat(), certainty, iso(now)),
    )
    log_event(conn, workspace_id, now, "contribution_created", "contribution", contribution_id,
              amount=to_string(value, currency), currency=currency, expected_date=expected.isoformat())
    return get_contribution(conn, workspace_id, contribution_id)


def receive_contribution(
    conn: sqlite3.Connection, workspace_id: str, contribution_id: str, received_on: date, now: datetime
) -> tuple[dict[str, str | None], bool]:
    """Mark received and credit the account exactly once. Returns (contribution, changed)."""
    contribution = get_contribution(conn, workspace_id, contribution_id)
    if contribution["status"] == "received":
        return contribution, False
    if contribution["status"] != "expected":
        raise DomainError(409, "invalid_state", "Only an expected contribution can be marked received.")
    updated = conn.execute(
        "UPDATE contributions SET status = 'received', received_on = ? WHERE workspace_id = ? AND id = ? AND status = 'expected'",
        (received_on.isoformat(), workspace_id, contribution_id),
    ).rowcount
    if updated != 1:  # pragma: no cover - guarded by the immediate transaction
        return get_contribution(conn, workspace_id, contribution_id), False
    post(conn, workspace_id, str(contribution["account_id"]), "contribution", Decimal(str(contribution["amount"])),
         "family_contribution", f"Contribution from {contribution['contributor']}", received_on, now,
         source_type="contribution", source_id=contribution_id)
    log_event(conn, workspace_id, now, "contribution_received", "contribution", contribution_id,
              amount=contribution["amount"], currency=contribution["currency"], received_on=received_on.isoformat())
    return get_contribution(conn, workspace_id, contribution_id), True


def cancel_contribution(conn: sqlite3.Connection, workspace_id: str, contribution_id: str, now: datetime) -> dict[str, str | None]:
    contribution = get_contribution(conn, workspace_id, contribution_id)
    if contribution["status"] != "expected":
        raise DomainError(409, "invalid_state", "Only an expected contribution can be cancelled.")
    conn.execute("UPDATE contributions SET status = 'cancelled' WHERE workspace_id = ? AND id = ?", (workspace_id, contribution_id))
    log_event(conn, workspace_id, now, "contribution_cancelled", "contribution", contribution_id)
    return get_contribution(conn, workspace_id, contribution_id)


# --- savings goals (allocations are labels on existing money, not transactions) ------


def list_goals(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, object]]:
    rows = conn.execute("SELECT * FROM savings_goals WHERE workspace_id = ? ORDER BY created_at, rowid", (workspace_id,)).fetchall()
    result = []
    for r in rows:
        target, allocated = Decimal(r["target_amount"]), Decimal(r["allocated_amount"])
        progress = min(Decimal(100), (allocated / target * 100).quantize(Decimal("0.1"))) if target > 0 else Decimal(0)
        result.append({
            "id": r["id"], "name": r["name"], "currency": r["currency"], "target_date": r["target_date"],
            "target_amount": r["target_amount"], "allocated_amount": r["allocated_amount"],
            "remaining": to_string(max(Decimal(0), target - allocated), r["currency"]),
            "progress_percent": format(progress, "f"),
        })
    return result


def create_goal(conn: sqlite3.Connection, workspace_id: str, *, name: str, target_amount: str, allocated_amount: str,
                currency: str, target_date: str | None, now: datetime) -> None:
    target = parse_amount(target_amount, currency)
    allocated = parse_amount(allocated_amount, currency)
    if target <= 0:
        raise DomainError(422, "invalid_amount", "The target must be greater than zero.")
    if target_date is not None:
        parse_date(target_date, "target_date")
    goal_id = new_id("goal")
    conn.execute(
        "INSERT INTO savings_goals (id, workspace_id, name, target_amount, allocated_amount, currency, target_date, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (goal_id, workspace_id, name, to_string(target, currency), to_string(allocated, currency), currency, target_date, iso(now)),
    )
    log_event(conn, workspace_id, now, "goal_created", "goal", goal_id, target=to_string(target, currency), currency=currency)


def update_goal_allocation(conn: sqlite3.Connection, workspace_id: str, goal_id: str, allocated_amount: str, now: datetime) -> None:
    row = conn.execute("SELECT currency FROM savings_goals WHERE workspace_id = ? AND id = ?", (workspace_id, goal_id)).fetchone()
    if row is None:
        raise not_found("Savings goal")
    allocated = parse_amount(allocated_amount, row["currency"])
    conn.execute("UPDATE savings_goals SET allocated_amount = ? WHERE workspace_id = ? AND id = ?",
                 (to_string(allocated, row["currency"]), workspace_id, goal_id))
    log_event(conn, workspace_id, now, "goal_updated", "goal", goal_id, allocated=to_string(allocated, row["currency"]))


# --- reserve policy ------------------------------------------------------------


def get_reserve(conn: sqlite3.Connection, workspace_id: str) -> dict[str, object] | None:
    row = conn.execute("SELECT account_id, floor_amount, strict FROM reserve_policies WHERE workspace_id = ?", (workspace_id,)).fetchone()
    if row is None:
        return None
    account = get_account_row(conn, workspace_id, row["account_id"])
    current = balance(conn, workspace_id, row["account_id"])
    floor = Decimal(row["floor_amount"])
    return {
        "account_id": row["account_id"],
        "account_name": account["name"],
        "currency": account["currency"],
        "floor_amount": to_string(floor, account["currency"]),
        "strict": bool(row["strict"]),
        "current_balance": to_string(current, account["currency"]),
        "headroom": to_string(current - floor, account["currency"]),
    }


def set_reserve(conn: sqlite3.Connection, workspace_id: str, account_id: str, floor_amount: str, now: datetime) -> dict[str, object] | None:
    account = get_account_row(conn, workspace_id, account_id)
    floor = parse_amount(floor_amount, account["currency"])
    conn.execute(
        "INSERT INTO reserve_policies (workspace_id, account_id, floor_amount, strict, updated_at) VALUES (?, ?, ?, 1, ?)"
        " ON CONFLICT(workspace_id) DO UPDATE SET account_id = excluded.account_id, floor_amount = excluded.floor_amount,"
        " updated_at = excluded.updated_at",
        (workspace_id, account_id, to_string(floor, account["currency"]), iso(now)),
    )
    log_event(conn, workspace_id, now, "reserve_updated", "reserve", workspace_id,
              floor=to_string(floor, account["currency"]), currency=account["currency"])
    return get_reserve(conn, workspace_id)
