"""Small shared helpers for services."""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import UTC, date, datetime

from ..errors import DomainError


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def parse_date(value: str, field: str = "date") -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise DomainError(422, "invalid_date", f"{field} must be a date in YYYY-MM-DD format.") from exc


def require_not_future(day: date, today: date, field: str) -> date:
    """Actual (recorded) money movements cannot be dated after the workspace's today.
    Future income and expenses belong in planning entries or expected contributions."""
    if day > today:
        raise DomainError(422, "future_date", f"{field} cannot be in the future. Record future money as a planned entry instead.",
                          field=field)
    return day


def log_event(
    conn: sqlite3.Connection,
    workspace_id: str,
    at: datetime,
    event_type: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    **details: object,
) -> None:
    conn.execute(
        "INSERT INTO activity_events (workspace_id, at, event_type, entity_type, entity_id, details)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (workspace_id, iso(at), event_type, entity_type, entity_id, json.dumps(details, sort_keys=True)),
    )


def recent_events(conn: sqlite3.Connection, workspace_id: str, limit: int = 20) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT id, at, event_type, entity_type, entity_id, details FROM activity_events"
        " WHERE workspace_id = ? ORDER BY id DESC LIMIT ?",
        (workspace_id, limit),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "at": r["at"],
            "event_type": r["event_type"],
            "entity_type": r["entity_type"],
            "entity_id": r["entity_id"],
            "details": json.loads(r["details"]),
        }
        for r in rows
    ]
