"""Dashboard figures derived only from the shared services (no separate arithmetic)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from ..money import to_string
from .budget import Period, Valuer, summary
from .cashflow import open_bills, project
from .common import recent_events
from .funding import get_reserve, list_contributions, list_goals
from .ledger import balances


def percent(part: Decimal, whole: Decimal) -> str | None:
    """Whole-number percentage (ROUND_HALF_EVEN) for display; None when the whole is not positive."""
    if whole <= 0:
        return None
    return str((part * 100 / whole).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def dashboard(conn: sqlite3.Connection, workspace_id: str, period: Period, display_currency: str, today: date) -> dict[str, object]:
    budget = summary(conn, workspace_id, period, display_currency)
    forecast = project(conn, workspace_id, today, max(period.end, today), display_currency)
    valuer = Valuer(conn, workspace_id, display_currency)
    d = display_currency

    bills = []
    for bill in open_bills(conn, workspace_id):
        value = valuer.value(Decimal(str(bill["amount"])), str(bill["currency"]))
        bills.append({**bill, "display_amount": None if value is None else to_string(value, d),
                      "overdue": date.fromisoformat(str(bill["due_date"])) < today})

    expected = Decimal(0)
    uncertain = Decimal(0)
    for c in list_contributions(conn, workspace_id):
        if c["status"] != "expected":
            continue
        value = valuer.value(Decimal(str(c["amount"])), str(c["currency"]))
        if value is None:
            continue
        if c["certainty"] == "expected":
            expected += value
        else:
            uncertain += value

    # Expense categories for the period, largest planned first. The share is of planned spending,
    # not of any balance; actual spending is reported beside it, never mixed into the share.
    planned_total = Decimal(str(budget["planned_expenses"]))
    categories = sorted(budget["categories"], key=lambda c: (-Decimal(str(c["planned"])), str(c["category"])))  # type: ignore[arg-type,index]
    categories = [{**c, "planned_share_percent": percent(Decimal(str(c["planned"])), planned_total)} for c in categories]  # type: ignore[index]

    # The reserve applies to one account; percentages are of that account's own balance.
    reserve = get_reserve(conn, workspace_id)
    if reserve is not None:
        account_balance = Decimal(str(reserve["current_balance"]))
        reserve = {**reserve,
                   "floor_percent": percent(Decimal(str(reserve["floor_amount"])), account_balance),
                   "headroom_percent": percent(Decimal(str(reserve["headroom"])), account_balance)}

    floor = forecast["reserve_floor"]
    lowest_confirmed = Decimal(str(forecast["lowest_confirmed"]))
    lowest_expected = Decimal(str(forecast["lowest_with_expected"]))
    floor_value = Decimal(str(floor)) if floor is not None else Decimal(0)
    return {
        "period": period.as_dict(),
        "display_currency": d,
        "today": today.isoformat(),
        "balances": balances(conn, workspace_id),
        "budget": {k: budget[k] for k in ("planned_income", "planned_expenses", "planned_remainder",
                                          "actual_income", "actual_expenses", "actual_net", "complete", "unconverted_count")},
        "forecast": {k: forecast[k] for k in ("current_funds", "projected_end_confirmed", "projected_end_with_expected",
                                              "lowest_confirmed", "lowest_confirmed_date", "to", "complete")},
        "categories": categories,
        "reserve": reserve,
        "upcoming_bills": bills,
        "funding": {
            "expected_contributions": to_string(expected, d),
            "uncertain_contributions_excluded": to_string(uncertain, d),
            # Shortfall below the reserve floor at the forecast's lowest point.
            "funding_gap_confirmed": to_string(max(Decimal(0), floor_value - lowest_confirmed), d),
            "funding_gap_with_expected": to_string(max(Decimal(0), floor_value - lowest_expected), d),
        },
        "goals": list_goals(conn, workspace_id),
        "recent_actions": recent_events(conn, workspace_id, 8),
        "valuation": budget["valuation"],
    }
