"""Workspace-scoped data access. Every query that touches private records
filters by workspace_id; IDs supplied by clients never grant access."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .clock import Clock
from .money import to_string
from .services.demo import seed_demo

SAMPLE_PROFILE = {"display_name": "Demo Student", "institution": "Example University (fictional)"}
DEFAULT_PREFERENCES = {"language": "en", "display_currency": "BDT", "time_zone": "Asia/Dhaka"}
# Fictional opening balances from the fixed test scenario in the demo specification.
SAMPLE_ACCOUNTS = (
    ("BDT everyday account (demo)", "BDT", "100000.00"),
    ("AUD student account (demo)", "AUD", "0.00"),
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- workspaces and sessions -------------------------------------------------


def create_workspace(conn: sqlite3.Connection, session_days: int, clock: Clock) -> tuple[str, str]:
    """Create a demo workspace with the fictional fixture scenario. Returns (workspace_id, raw session token).

    Session expiry always uses real time; the seeded scenario uses the (possibly simulated) clock."""
    now = utc_now()
    workspace_id = new_id("ws")
    conn.execute(
        "INSERT INTO workspaces (id, created_at) VALUES (?, ?)", (workspace_id, iso(now))
    )
    conn.execute(
        "INSERT INTO profiles (workspace_id, display_name, institution, updated_at)"
        " VALUES (?, ?, ?, ?)",
        (workspace_id, SAMPLE_PROFILE["display_name"], SAMPLE_PROFILE["institution"], iso(now)),
    )
    conn.execute(
        "INSERT INTO preferences (workspace_id, language, display_currency, time_zone, updated_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (
            workspace_id,
            DEFAULT_PREFERENCES["language"],
            DEFAULT_PREFERENCES["display_currency"],
            DEFAULT_PREFERENCES["time_zone"],
            iso(now),
        ),
    )
    sim_now = clock.now()
    today = clock.today(DEFAULT_PREFERENCES["time_zone"])
    account_ids = []
    for position, (name, currency, balance) in enumerate(SAMPLE_ACCOUNTS):
        account_id = new_id("acct")
        account_ids.append(account_id)
        conn.execute(
            "INSERT INTO accounts (id, workspace_id, name, currency, opening_balance,"
            " opening_date, created_at, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (account_id, workspace_id, name, currency, balance, today.isoformat(), iso(now), position),
        )
    seed_demo(conn, workspace_id, account_ids[0], sim_now, today)
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token_hash, workspace_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (hash_token(token), workspace_id, iso(now), iso(now + timedelta(days=session_days))),
    )
    return workspace_id, token


def workspace_for_token(conn: sqlite3.Connection, token: str) -> str | None:
    row = conn.execute(
        "SELECT workspace_id, expires_at FROM sessions WHERE token_hash = ?", (hash_token(token),)
    ).fetchone()
    if row is None or row["expires_at"] <= iso(utc_now()):
        return None
    return str(row["workspace_id"])


def delete_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (iso(utc_now()),))


# --- profile and preferences --------------------------------------------------


def get_profile(conn: sqlite3.Connection, workspace_id: str) -> dict[str, str]:
    row = conn.execute(
        "SELECT display_name, institution, updated_at FROM profiles WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()
    return dict(row)


def update_profile(
    conn: sqlite3.Connection, workspace_id: str, display_name: str, institution: str
) -> None:
    conn.execute(
        "UPDATE profiles SET display_name = ?, institution = ?, updated_at = ? WHERE workspace_id = ?",
        (display_name, institution, iso(utc_now()), workspace_id),
    )


def get_preferences(conn: sqlite3.Connection, workspace_id: str) -> dict[str, str]:
    row = conn.execute(
        "SELECT language, display_currency, time_zone, updated_at FROM preferences"
        " WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()
    return dict(row)


def update_preferences(
    conn: sqlite3.Connection, workspace_id: str, language: str, display_currency: str, time_zone: str
) -> None:
    conn.execute(
        "UPDATE preferences SET language = ?, display_currency = ?, time_zone = ?, updated_at = ?"
        " WHERE workspace_id = ?",
        (language, display_currency, time_zone, iso(utc_now()), workspace_id),
    )


# --- accounts -----------------------------------------------------------------


def _account(row: sqlite3.Row) -> dict[str, str]:
    return {
        "id": row["id"],
        "name": row["name"],
        "currency": row["currency"],
        "opening_balance": to_string(Decimal(row["opening_balance"]), row["currency"]),
        "opening_date": row["opening_date"],
    }


def list_accounts(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, str]]:
    rows = conn.execute(
        "SELECT id, name, currency, opening_balance, opening_date FROM accounts"
        " WHERE workspace_id = ? ORDER BY position, id",
        (workspace_id,),
    ).fetchall()
    return [_account(r) for r in rows]


def get_account(conn: sqlite3.Connection, workspace_id: str, account_id: str) -> dict[str, str] | None:
    row = conn.execute(
        "SELECT id, name, currency, opening_balance, opening_date FROM accounts"
        " WHERE workspace_id = ? AND id = ?",
        (workspace_id, account_id),
    ).fetchone()
    return _account(row) if row else None


# --- AI connection checks -------------------------------------------------------


def record_ai_check(conn: sqlite3.Connection, model: str, ok: bool, outcome: str) -> None:
    conn.execute(
        "INSERT INTO ai_checks (checked_at, model, ok, outcome) VALUES (?, ?, ?, ?)",
        (iso(utc_now()), model, 1 if ok else 0, outcome),
    )


def latest_ai_check(conn: sqlite3.Connection) -> dict[str, object] | None:
    row = conn.execute(
        "SELECT checked_at, model, ok, outcome FROM ai_checks ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return {"checked_at": row["checked_at"], "model": row["model"], "ok": bool(row["ok"]), "outcome": row["outcome"]}
