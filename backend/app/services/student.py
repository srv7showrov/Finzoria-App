"""Financial Growth & Student Funding: application tracker, checklists and the work-income calculator.

Checklist items and resource links are fixed in code (their wording lives in the frontend
catalogs); only the done/not-done state is stored. Nothing here is legal, visa, tax or credit
advice and the calculator does not model any tax system: deductions are the user's own
percentage assumption."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from ..errors import DomainError, not_found
from ..money import MoneyError, parse_decimal, quantize, to_string, validate_currency
from .common import iso, log_event, new_id, parse_date

APPLICATION_STATUSES = ("planning", "applied", "awarded", "declined", "withdrawn")
OPEN_APPLICATION_STATUSES = ("planning", "applied")

# Keys only; the text is translated in the UI. Australia is the one supported jurisdiction.
CHECKLISTS: dict[str, tuple[str, ...]] = {
    "setup": ("budget_set", "reserve_set", "bills_listed", "family_plan", "fee_compare", "emergency_contacts"),
    "credit_au": ("learn_report", "free_report", "check_errors", "pay_on_time", "avoid_bnpl", "scam_awareness"),
    "arrival": ("tuition_due", "first_month", "local_account", "phone_plan", "health_cover", "keep_records"),
}
CHECKLIST_KEYS = frozenset(f"{group}.{item}" for group, items in CHECKLISTS.items() for item in items)

# Official starting points only. These pages could NOT be fetched from the build environment
# (network blocked, checked 2026-10-19), so no amounts, deadlines or eligibility facts are shown.
RESOURCES: tuple[dict[str, str], ...] = (
    {"key": "study_australia_scholarships", "url": "https://www.studyaustralia.gov.au/en/plan-your-studies/scholarships-and-funding", "kind": "scholarship", "jurisdiction": "AU"},
    {"key": "australia_awards", "url": "https://www.dfat.gov.au/people-to-people/australia-awards", "kind": "scholarship", "jurisdiction": "AU"},
    {"key": "destination_australia", "url": "https://www.education.gov.au/destination-australia", "kind": "scholarship", "jurisdiction": "AU"},
    {"key": "moneysmart_credit", "url": "https://moneysmart.gov.au/managing-debt/credit-scores-and-credit-reports", "kind": "credit", "jurisdiction": "AU"},
    {"key": "scamwatch", "url": "https://www.scamwatch.gov.au/", "kind": "safety", "jurisdiction": "AU"},
)
RESOURCES_CHECKED = {"date": "2026-10-19", "status": "not_verified", "reason": "network_blocked"}

MAX_HOURS_PER_WEEK = Decimal(80)
MAX_WEEKS = 104


# --- application tracker -----------------------------------------------------------


def _application(row: sqlite3.Row) -> dict[str, object]:
    return {k: row[k] for k in ("id", "name", "provider", "status", "deadline", "notes", "updated_at")}


def list_applications(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT * FROM funding_applications WHERE workspace_id = ?"
        " ORDER BY deadline IS NULL, deadline, created_at, rowid", (workspace_id,)
    ).fetchall()
    return [_application(r) for r in rows]


def _status(value: str) -> str:
    if value not in APPLICATION_STATUSES:
        raise DomainError(422, "invalid_status", "Unknown application status.")
    return value


def _deadline(value: str | None) -> str | None:
    return parse_date(value, "deadline").isoformat() if value else None


def create_application(conn: sqlite3.Connection, workspace_id: str, *, name: str, provider: str, status: str,
                       deadline: str | None, notes: str, now: datetime) -> dict[str, object]:
    app_id = new_id("app")
    conn.execute(
        "INSERT INTO funding_applications (id, workspace_id, name, provider, status, deadline, notes, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (app_id, workspace_id, name, provider, _status(status), _deadline(deadline), notes, iso(now), iso(now)),
    )
    log_event(conn, workspace_id, now, "funding_application_added", "funding_application", app_id, status=status)
    return get_application(conn, workspace_id, app_id)


def get_application(conn: sqlite3.Connection, workspace_id: str, app_id: str) -> dict[str, object]:
    row = conn.execute("SELECT * FROM funding_applications WHERE workspace_id = ? AND id = ?", (workspace_id, app_id)).fetchone()
    if row is None:
        raise not_found("Application")
    return _application(row)


def update_application(conn: sqlite3.Connection, workspace_id: str, app_id: str, *, name: str, provider: str, status: str,
                       deadline: str | None, notes: str, now: datetime) -> dict[str, object]:
    get_application(conn, workspace_id, app_id)
    conn.execute(
        "UPDATE funding_applications SET name = ?, provider = ?, status = ?, deadline = ?, notes = ?, updated_at = ?"
        " WHERE workspace_id = ? AND id = ?",
        (name, provider, _status(status), _deadline(deadline), notes, iso(now), workspace_id, app_id),
    )
    log_event(conn, workspace_id, now, "funding_application_updated", "funding_application", app_id, status=status)
    return get_application(conn, workspace_id, app_id)


def delete_application(conn: sqlite3.Connection, workspace_id: str, app_id: str, now: datetime) -> None:
    get_application(conn, workspace_id, app_id)
    conn.execute("DELETE FROM funding_applications WHERE workspace_id = ? AND id = ?", (workspace_id, app_id))
    log_event(conn, workspace_id, now, "funding_application_removed", "funding_application", app_id)


# --- checklists ---------------------------------------------------------------------


def checklists(conn: sqlite3.Connection, workspace_id: str) -> dict[str, object]:
    done = {r["item_key"] for r in conn.execute(
        "SELECT item_key FROM checklist_state WHERE workspace_id = ? AND done = 1", (workspace_id,))}
    return {
        "groups": [
            {"key": group, "items": [{"key": f"{group}.{item}", "done": f"{group}.{item}" in done} for item in items]}
            for group, items in CHECKLISTS.items()
        ],
        "jurisdiction": "AU",
    }


def set_checklist_item(conn: sqlite3.Connection, workspace_id: str, item_key: str, done: bool, now: datetime) -> dict[str, object]:
    if item_key not in CHECKLIST_KEYS:
        raise not_found("Checklist item")
    conn.execute(
        "INSERT INTO checklist_state (workspace_id, item_key, done, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (workspace_id, item_key) DO UPDATE SET done = excluded.done, updated_at = excluded.updated_at",
        (workspace_id, item_key, 1 if done else 0, iso(now)),
    )
    return checklists(conn, workspace_id)


# --- work-income calculator ------------------------------------------------------------


def work_income(*, hourly_rate: str, hours_per_week: str, weeks: int, currency: str, basis: str,
                deduction_percent: str) -> dict[str, object]:
    """Estimate earnings from the user's own assumptions. `basis` says whether the hourly rate is
    before (gross) or after (net) deductions; deductions apply only to a gross rate and are the
    user's own percentage, not a tax calculation. Rounded once, at the end, per currency."""
    currency = validate_currency(currency)
    rate = parse_decimal(hourly_rate)
    hours = parse_decimal(hours_per_week)
    percent = parse_decimal(deduction_percent)
    if rate <= 0:
        raise MoneyError("Hourly rate must be greater than zero")
    if hours <= 0 or hours > MAX_HOURS_PER_WEEK:
        raise MoneyError("Hours per week must be between 0 and 80")
    if not 1 <= weeks <= MAX_WEEKS:
        raise MoneyError("Weeks must be between 1 and 104")
    if basis not in ("gross", "net"):
        raise MoneyError("Basis must be gross or net")
    if percent < 0 or percent >= 100:
        raise MoneyError("Deduction percent must be at least 0 and below 100")
    if basis == "net":
        percent = Decimal(0)
    weekly_gross = rate * hours
    weekly_net = weekly_gross * (Decimal(100) - percent) / Decimal(100)
    total_gross = weekly_gross * weeks
    total_net = weekly_net * weeks
    return {
        "currency": currency,
        "basis": basis,
        "deduction_percent": format(percent, "f"),
        "weeks": weeks,
        "hours_per_week": format(hours, "f"),
        "weekly_gross": to_string(weekly_gross, currency) if basis == "gross" else None,
        "weekly_net": to_string(weekly_net, currency),
        "total_gross": to_string(total_gross, currency) if basis == "gross" else None,
        "total_net": to_string(total_net, currency),
        "deductions_total": to_string(total_gross - quantize(total_net, currency), currency) if basis == "gross" else None,
        "assumptions": ["user_rate", "user_deductions" if basis == "gross" else "net_rate_given", "no_tax_engine", "check_work_rules"],
    }


def resources() -> dict[str, object]:
    return {"resources": list(RESOURCES), "checked": RESOURCES_CHECKED, "jurisdiction": "AU"}


def overview(conn: sqlite3.Connection, workspace_id: str, today: date) -> dict[str, object]:
    return {
        "applications": list_applications(conn, workspace_id),
        "checklists": checklists(conn, workspace_id),
        **resources(),
        "today": today.isoformat(),
    }
