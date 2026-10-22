"""Period reports built only from the shared budget, dashboard and ledger services.

Valuation policy (same as the dashboard): originals are converted to the display
currency with the latest rate snapshot per pair at the time the report is viewed.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import date
from decimal import Decimal

from ..money import to_string
from .budget import Period, Valuer, summary
from .dashboard import dashboard

_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def report(conn: sqlite3.Connection, workspace_id: str, period: Period, display_currency: str, today: date) -> dict[str, object]:
    s = summary(conn, workspace_id, period, display_currency)
    d = dashboard(conn, workspace_id, period, display_currency, today)
    valuer = Valuer(conn, workspace_id, display_currency)
    fee_items = [t for t in s["actual_items"] if t["kind"] == "fee"]  # type: ignore[union-attr]
    fees_total = Decimal(0)
    unvalued_fees = 0
    for fee in fee_items:
        value = valuer.value(Decimal(str(fee["amount"])), str(fee["currency"]))
        if value is None:
            unvalued_fees += 1
        else:
            fees_total += value
    return {
        "period": s["period"],
        "display_currency": display_currency,
        "generated_for": today.isoformat(),
        "totals": {k: s[k] for k in ("planned_income", "planned_expenses", "planned_remainder",
                                     "actual_income", "actual_expenses", "actual_net")},
        "categories": s["categories"],
        "funding": d["funding"],
        "forecast": d["forecast"],
        "reserve": d["reserve"],
        "goals": d["goals"],
        "transfer_fees": {
            "items": [{"date": f["occurred_on"], "description": f["description"], "amount": f["amount"],
                       "currency": f["currency"]} for f in fee_items],
            "total": to_string(fees_total, display_currency),
            "unvalued_count": unvalued_fees,
        },
        "complete": bool(s["complete"]) and unvalued_fees == 0,
        "unconverted_count": int(s["unconverted_count"]) + unvalued_fees,  # type: ignore[call-overload]
        "valuation": s["valuation"],
        "planned_items": s["planned_items"],
        "actual_items": s["actual_items"],
    }


def safe_cell(value: object) -> str:
    """Neutralize spreadsheet formulas: text starting with = + - @ tab or CR gets a leading
    apostrophe. Plain decimal numbers (amounts) are left as numbers."""
    text = "" if value is None else str(value)
    if text and not _NUMBER.fullmatch(text) and text.startswith(_FORMULA_START):
        return "'" + text
    return text


def _signed(amount: object, debit: bool) -> str:
    """Negate an unsigned decimal string for a debit, keeping its exact digits (no float)."""
    if amount is None or amount == "":
        return ""
    value = Decimal(str(amount))
    return format(-value if debit and value != 0 else value, "f")


def report_csv(data: dict[str, object]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    period = data["period"]
    d = data["display_currency"]
    writer.writerow(["Finzoria report (demo data)", f"{period['start']} to {period['end']}", f"display currency {d}"])  # type: ignore[index]
    writer.writerow(["section", "date", "kind", "category", "description", "amount", "currency", f"value_{d}", "status"])
    for item in data["planned_items"]:  # type: ignore[union-attr]
        writer.writerow([safe_cell(x) for x in ("planned", item["date"], item["kind"], item["category"], item["description"],
                                                item["amount"], item["currency"], item["display_amount"] or "",
                                                "recorded" if item.get("fulfilled") else "")])
    for item in data["actual_items"]:  # type: ignore[union-attr]
        # Actual rows are signed: debits negative, credits positive, for both the original amount
        # and its converted value. A missing rate leaves the converted value empty.
        debit = item["direction"] != "credit"
        writer.writerow([safe_cell(x) for x in ("actual", item["occurred_on"], item["kind"], item["category"], item["description"],
                                                _signed(item["amount"], debit), item["currency"],
                                                _signed(item["display_amount"], debit), "")])
    for key, value in data["totals"].items():  # type: ignore[union-attr]
        writer.writerow([safe_cell(x) for x in ("total", "", key, "", "", value, d, value, "")])
    writer.writerow([safe_cell(x) for x in ("total", "", "transfer_fees", "", "", data["transfer_fees"]["total"], d,  # type: ignore[index]
                                            data["transfer_fees"]["total"], "")])  # type: ignore[index]
    return out.getvalue()
