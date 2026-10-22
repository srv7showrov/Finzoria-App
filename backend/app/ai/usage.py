"""Local log of model request attempts and the local request guards.

Every request this app sends to a model provider (chat rounds, invoice extraction,
connection checks) is recorded, including failed attempts. The counts are this app's own
records: they are NOT the provider's remaining quota, which can differ (other apps using
the same key or project, provider-side changes, resets on the provider's schedule).

Times are real wall-clock UTC even when the app runs on the simulation clock, because
provider limits are measured in real time.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from ..db import Database
from ..errors import DomainError
from ..services.common import iso


def _now() -> datetime:
    return datetime.now(UTC)


def record(db: Database, *, workspace_id: str | None, provider: str, model: str, purpose: str, ok: bool,
           error_code: str | None, at: datetime | None = None) -> None:
    at = at or _now()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO ai_requests (workspace_id, at, provider, model, purpose, ok, error_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workspace_id, iso(at), provider, model, purpose, 1 if ok else 0, error_code))


def counts(conn: sqlite3.Connection, now: datetime | None = None) -> dict[str, int]:
    """App-wide attempts in the last minute and last 24 hours (rolling windows)."""
    now = now or _now()
    minute = conn.execute("SELECT COUNT(*) FROM ai_requests WHERE at > ?", (iso(now - timedelta(minutes=1)),)).fetchone()[0]
    day = conn.execute("SELECT COUNT(*) FROM ai_requests WHERE at > ?", (iso(now - timedelta(days=1)),)).fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM ai_requests WHERE at > ? AND ok = 0",
                          (iso(now - timedelta(days=1)),)).fetchone()[0]
    return {"last_minute": int(minute), "last_24h": int(day), "failed_last_24h": int(failed)}


def blocked_by(conn: sqlite3.Connection, adapter: object, now: datetime | None = None) -> str | None:
    """Return "request_limit_minute" / "request_limit_day" if the next request would exceed a local guard."""
    c = counts(conn, now)
    per_day = getattr(adapter, "requests_per_day", None)
    per_minute = getattr(adapter, "requests_per_minute", None)
    if per_day and c["last_24h"] >= per_day:
        return "request_limit_day"
    if per_minute and c["last_minute"] >= per_minute:
        return "request_limit_minute"
    return None


def require_budget(db: Database, adapter: object, now: datetime | None = None) -> None:
    """Refuse before any model call (and before anything is saved) when a local guard is reached."""
    with db.read() as conn:
        reason = blocked_by(conn, adapter, now)
    if reason == "request_limit_day":
        raise DomainError(429, "assistant_daily_limit",
                          "This app's daily AI request limit is reached. Try again tomorrow; calculators and forms still work.")
    if reason == "request_limit_minute":
        raise DomainError(429, "assistant_minute_limit", "Too many AI requests this minute. Wait a minute and try again.")


def summary(db: Database, adapter: object, now: datetime | None = None) -> dict[str, object]:
    with db.read() as conn:
        c = counts(conn, now)
    return {**c, "limits": {"per_minute": getattr(adapter, "requests_per_minute", None),
                            "per_day": getattr(adapter, "requests_per_day", None),
                            "per_turn": getattr(adapter, "requests_per_turn", None)},
            "note": "Counts of this app's own request attempts, including failures. Not the provider's remaining quota."}
