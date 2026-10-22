"""Workspace export, reset and delete. Each acts only on the session's own workspace."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from .common import iso

# Exported tables. Session token hashes are never exported.
EXPORT_TABLES = (
    "profiles", "preferences", "accounts", "transactions", "budget_entries", "plan_fulfilments", "bills",
    "contributions", "savings_goals", "reserve_policies", "fx_snapshots", "rate_targets", "quotes",
    "payment_proposals", "executions", "refunds", "activity_events", "conversations", "assistant_messages",
    "assistant_tool_calls", "assistant_actions", "ai_requests", "funding_applications", "checklist_state",
)


def export(conn: sqlite3.Connection, workspace_id: str, now: datetime) -> dict[str, object]:
    tables: dict[str, list[dict[str, object]]] = {}
    for table in EXPORT_TABLES:  # fixed allowlist, never user input
        rows = conn.execute(f"SELECT * FROM {table} WHERE workspace_id = ? ORDER BY rowid", (workspace_id,)).fetchall()
        tables[table] = [{k: r[k] for k in r.keys() if k != "workspace_id"} for r in rows]
    for row in tables["activity_events"]:
        if isinstance(row.get("details"), str):
            row["details"] = json.loads(str(row["details"]))
    return {
        "format": "finzoria-workspace-export",
        "version": 1,
        "exported_at": iso(now),
        "data_mode": "demo",
        "note": "Fictional demo data. Amounts are decimal strings in their original currencies. Payments were simulated.",
        "tables": tables,
    }


def delete_workspace(conn: sqlite3.Connection, workspace_id: str) -> None:
    """Removes the workspace and, through ON DELETE CASCADE, every record and session in it."""
    conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
