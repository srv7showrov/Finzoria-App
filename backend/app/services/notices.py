"""In-app deadline notices and the calendar (.ics) export.

Notices are computed when a page is viewed; there is no background notification system.
Deadlines are date-only: calendar events are all-day (VALUE=DATE) so they never shift
across time zones, and the export states the workspace time zone."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from .bills import list_bills
from .funding import list_contributions
from .student import OPEN_APPLICATION_STATUSES, list_applications

NOTICE_WINDOW_DAYS = 14


def deadlines(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for b in list_bills(conn, workspace_id):
        if b["status"] == "open":
            items.append({"kind": "bill", "id": b["id"], "date": b["due_date"], "title": b["description"],
                          "detail": b["payee"], "amount": b["amount"], "currency": b["currency"]})
    for c in list_contributions(conn, workspace_id):
        if c["status"] == "expected":
            items.append({"kind": "contribution", "id": c["id"], "date": c["expected_date"], "title": c["contributor"],
                          "detail": c["certainty"], "amount": c["amount"], "currency": c["currency"]})
    for a in list_applications(conn, workspace_id):
        if a["deadline"] and a["status"] in OPEN_APPLICATION_STATUSES:
            items.append({"kind": "application", "id": a["id"], "date": a["deadline"], "title": a["name"],
                          "detail": a["provider"], "amount": None, "currency": None})
    items.sort(key=lambda i: (str(i["date"]), str(i["kind"]), str(i["id"])))
    return items


def notices(conn: sqlite3.Connection, workspace_id: str, today: date) -> dict[str, object]:
    horizon = today + timedelta(days=NOTICE_WINDOW_DAYS)
    out = []
    for item in deadlines(conn, workspace_id):
        day = date.fromisoformat(str(item["date"]))
        if day > horizon:
            continue
        out.append({**item, "days": (day - today).days, "state": "overdue" if day < today else "today" if day == today else "soon"})
    return {"notices": out, "today": today.isoformat(), "window_days": NOTICE_WINDOW_DAYS, "background": False}


def _escape(text: object) -> str:
    """RFC 5545 TEXT escaping; also drops other control characters from user text."""
    s = "" if text is None else str(text)
    s = "".join(ch for ch in s if ch in "\n" or ch >= " ")
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Fold at 75 octets without splitting UTF-8 characters."""
    out, current = [], ""
    for ch in line:
        limit = 75 if not out else 74
        if len((current + ch).encode()) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0]] + [" " + part for part in out[1:]]


KIND_LABEL = {"bill": "Bill due", "contribution": "Expected contribution", "application": "Application deadline"}


def calendar_ics(conn: sqlite3.Connection, workspace_id: str, time_zone: str, now: datetime) -> str:
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Finzoria//Demo planner//EN", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape('Finzoria deadlines (demo data)')}", f"X-WR-TIMEZONE:{_escape(time_zone)}",
    ]
    for item in deadlines(conn, workspace_id):
        day = date.fromisoformat(str(item["date"]))
        amount = f" {item['currency']} {item['amount']}" if item["amount"] else ""
        description = (f"{KIND_LABEL[str(item['kind'])]}{amount}. Date-only deadline; workspace time zone {time_zone}. "
                       "Demo data. Simulated planner, no real payment.")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{item['kind']}-{item['id']}@finzoria.invalid",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_escape(KIND_LABEL[str(item['kind'])] + ': ' + str(item['title']))}",
            f"DESCRIPTION:{_escape(description)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(part + "\r\n" for line in lines for part in _fold(line))
