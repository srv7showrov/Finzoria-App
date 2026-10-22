"""Actual balances and posted transactions.

Balance = opening balance (counted once) + credits - debits. Money is summed in
Python Decimal from stored strings, never with SQL arithmetic on text.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from ..errors import DomainError, not_found
from ..money import to_string
from .common import iso, new_id

CREDIT_KINDS = {"income": "credit", "contribution": "credit", "expense": "debit", "payment": "debit", "fee": "debit"}
# Kinds that count as spending/income in budgets and reports.
SPENDING_KINDS = {"expense", "payment", "fee"}
INCOME_KINDS = {"income", "contribution"}


def get_account_row(conn: sqlite3.Connection, workspace_id: str, account_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, name, currency, opening_balance, opening_date FROM accounts WHERE workspace_id = ? AND id = ?",
        (workspace_id, account_id),
    ).fetchone()
    if row is None:
        raise not_found("Account")
    return row


def balance(conn: sqlite3.Connection, workspace_id: str, account_id: str) -> Decimal:
    account = get_account_row(conn, workspace_id, account_id)
    total = Decimal(account["opening_balance"])
    for r in conn.execute(
        "SELECT direction, amount FROM transactions WHERE workspace_id = ? AND account_id = ?",
        (workspace_id, account_id),
    ):
        amount = Decimal(r["amount"])
        total += amount if r["direction"] == "credit" else -amount
    return total


def balances(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, str]]:
    rows = conn.execute(
        "SELECT id, name, currency, opening_balance, opening_date FROM accounts WHERE workspace_id = ? ORDER BY position, id",
        (workspace_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "currency": r["currency"],
            "opening_balance": to_string(Decimal(r["opening_balance"]), r["currency"]),
            "opening_date": r["opening_date"],
            "balance": to_string(balance(conn, workspace_id, r["id"]), r["currency"]),
        }
        for r in rows
    ]


def post(
    conn: sqlite3.Connection,
    workspace_id: str,
    account_id: str,
    kind: str,
    amount: Decimal,
    category: str,
    description: str,
    occurred_on: date,
    now: datetime,
    source_type: str | None = None,
    source_id: str | None = None,
) -> str:
    account = get_account_row(conn, workspace_id, account_id)
    if amount <= 0:
        raise DomainError(422, "invalid_amount", "Amounts must be greater than zero.")
    transaction_id = new_id("txn")
    conn.execute(
        "INSERT INTO transactions (id, workspace_id, account_id, kind, direction, category, description, amount,"
        " currency, occurred_on, source_type, source_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            transaction_id,
            workspace_id,
            account_id,
            kind,
            CREDIT_KINDS[kind],
            category,
            description,
            to_string(amount, account["currency"]),
            account["currency"],
            occurred_on.isoformat(),
            source_type,
            source_id,
            iso(now),
        ),
    )
    return transaction_id


def list_transactions(
    conn: sqlite3.Connection, workspace_id: str, start: date | None = None, end: date | None = None
) -> list[dict[str, str | None]]:
    sql = (
        "SELECT t.id, t.account_id, a.name AS account_name, t.kind, t.direction, t.category, t.description, t.amount,"
        " t.currency, t.occurred_on, t.source_type, t.source_id FROM transactions t"
        " JOIN accounts a ON a.id = t.account_id AND a.workspace_id = t.workspace_id WHERE t.workspace_id = ?"
    )
    params: list[object] = [workspace_id]
    if start is not None:
        sql += " AND t.occurred_on >= ?"
        params.append(start.isoformat())
    if end is not None:
        sql += " AND t.occurred_on <= ?"
        params.append(end.isoformat())
    sql += " ORDER BY t.occurred_on DESC, t.created_at DESC, t.rowid DESC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]
