"""User confirmation of changes the assistant prepared. Only these explicit UI calls save
anything; each pending action can be confirmed or dismissed once."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from ..errors import DomainError, not_found
from ..services import bills, budget, funding
from ..services.common import iso, log_event


def _row(conn: sqlite3.Connection, workspace_id: str, action_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM assistant_actions WHERE workspace_id = ? AND id = ?", (workspace_id, action_id)).fetchone()
    if row is None:
        raise not_found("Prepared action")
    return row


def as_dict(row: sqlite3.Row) -> dict[str, object]:
    return {"id": row["id"], "kind": row["kind"], "payload": json.loads(row["payload"]), "status": row["status"],
            "result_id": row["result_id"], "status_reason": row["status_reason"], "conversation_id": row["conversation_id"]}


def list_actions(conn: sqlite3.Connection, workspace_id: str, conversation_id: str | None = None) -> list[dict[str, object]]:
    sql = "SELECT * FROM assistant_actions WHERE workspace_id = ?"
    params: list[object] = [workspace_id]
    if conversation_id:
        sql += " AND conversation_id = ?"
        params.append(conversation_id)
    return [as_dict(r) for r in conn.execute(sql + " ORDER BY created_at, rowid", params).fetchall()]


def confirm(conn: sqlite3.Connection, workspace_id: str, action_id: str, now: datetime, today: date) -> dict[str, object]:
    """Save the prepared change through the normal service (which validates again)."""
    row = _row(conn, workspace_id, action_id)
    if row["status"] != "pending":
        raise DomainError(409, "action_not_pending", "This prepared change was already confirmed or dismissed.")
    payload = json.loads(row["payload"])
    if row["kind"] == "budget_entry":
        result_id = str(budget.create_entry(conn, workspace_id, now=now, **payload)["id"])
    elif row["kind"] == "bill":
        result_id = str(bills.create_bill(conn, workspace_id, now=now, **payload)["id"])
    else:  # contribution: always created as EXPECTED; receiving money stays a separate user action
        result_id = str(funding.create_contribution(
            conn, workspace_id, account_id=payload["account_id"], contributor=payload["contributor"], amount=payload["amount"],
            expected_date=payload["expected_date"], certainty=payload["certainty"], now=now)["id"])
    updated = conn.execute(
        "UPDATE assistant_actions SET status = 'confirmed', result_id = ?, updated_at = ? WHERE workspace_id = ? AND id = ?"
        " AND status = 'pending'", (result_id, iso(now), workspace_id, action_id),
    ).rowcount
    if updated != 1:  # pragma: no cover - guarded by the immediate transaction
        raise DomainError(409, "action_not_pending", "This prepared change was already confirmed or dismissed.")
    log_event(conn, workspace_id, now, "assistant_action_confirmed", "assistant_action", action_id, kind=row["kind"], result_id=result_id)
    return as_dict(_row(conn, workspace_id, action_id))


def dismiss(conn: sqlite3.Connection, workspace_id: str, action_id: str, now: datetime) -> dict[str, object]:
    row = _row(conn, workspace_id, action_id)
    if row["status"] != "pending":
        raise DomainError(409, "action_not_pending", "This prepared change was already confirmed or dismissed.")
    conn.execute("UPDATE assistant_actions SET status = 'dismissed', updated_at = ? WHERE workspace_id = ? AND id = ?",
                 (iso(now), workspace_id, action_id))
    log_event(conn, workspace_id, now, "assistant_action_dismissed", "assistant_action", action_id, kind=row["kind"])
    return as_dict(_row(conn, workspace_id, action_id))
