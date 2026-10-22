"""Daily projected cash flow and what-if scenarios.

Projections are forecasts, never available cash. Date-only semantics:

- Actual (recorded) activity is already in today's account balances; it is never
  dated in the future (see common.require_not_future).
- Planned entries are forecasts. An occurrence dated today or later is outstanding
  and is projected on its own date; occurrences before today are treated as past
  and are not projected. An occurrence explicitly recorded as paid/received
  (budget.record_occurrence) is linked to its actual transaction and is no longer
  projected. Transactions entered separately are never matched to plans.
- Open bills due today or later are projected on their due date; overdue open
  bills are still owed and are projected today.
- Contributions still marked expected (certainty "expected") are projected on
  their expected date, or today if that date has passed, and only in the
  "with expected funding" line. Uncertain contributions are excluded from both.
- On the same day, outflows are applied before inflows (conservative low point).

Scenarios never write to the database.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal

from ..errors import DomainError
from ..money import parse_amount, to_string
from . import rates as rates_service
from .budget import Period, Valuer, fulfilled_occurrences, get_entry, list_entries, occurrences, planned_items
from .common import parse_date
from .funding import get_contribution, get_reserve, list_contributions
from .ledger import balance, balances
from .transfer_routes import ROUTES, cost, require_route_currency


def open_bills(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT id, description, payee, category, amount, currency, due_date, status, version FROM bills"
        " WHERE workspace_id = ? AND status = 'open' ORDER BY due_date, rowid",
        (workspace_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def project(
    conn: sqlite3.Connection,
    workspace_id: str,
    today: date,
    end: date,
    display_currency: str,
    *,
    contribution_dates: dict[str, date] | None = None,
    entry_amounts: dict[str, str] | None = None,
) -> dict[str, object]:
    """Project from today to end (inclusive). Overrides apply to this calculation only."""
    valuer = Valuer(conn, workspace_id, display_currency)
    d = display_currency
    unconverted = 0

    current = Decimal(0)
    for acct in balances(conn, workspace_id):
        value = valuer.value(Decimal(acct["balance"]), acct["currency"])
        if value is None:
            unconverted += 1
        else:
            current += value

    events: list[tuple[date, str, Decimal, str, str]] = []  # (date, kind, signed display amount, label, track)
    # Items due today are still outstanding; they belong to today, not tomorrow.
    horizon_start = today
    if end >= horizon_start:
        for item in planned_items(conn, workspace_id, horizon_start, end, valuer):
            if item["fulfilled"]:
                continue  # already an actual transaction, included in today's balances
            amount = item["display_amount"]
            if entry_amounts and item["entry_id"] in entry_amounts:
                entry_currency = str(item["currency"])
                override = parse_amount(entry_amounts[str(item["entry_id"])], entry_currency)
                amount = None if (v := valuer.value(override, entry_currency)) is None else to_string(v, d)
            if amount is None:
                unconverted += 1
                continue
            sign = 1 if item["kind"] == "income" else -1
            events.append((date.fromisoformat(str(item["date"])), f"planned_{item['kind']}", sign * Decimal(str(amount)),
                           str(item["description"] or item["category"]), "confirmed"))
    for bill in open_bills(conn, workspace_id):
        due = date.fromisoformat(str(bill["due_date"]))
        # Overdue open bills are still owed: project them today.
        due = max(due, horizon_start)
        if due > end:
            continue
        value = valuer.value(Decimal(str(bill["amount"])), str(bill["currency"]))
        if value is None:
            unconverted += 1
            continue
        events.append((due, "bill", -value, str(bill["description"]), "confirmed"))
    for c in list_contributions(conn, workspace_id):
        if c["status"] != "expected" or c["certainty"] != "expected":
            continue
        when = (contribution_dates or {}).get(str(c["id"]), date.fromisoformat(str(c["expected_date"])))
        when = max(when, horizon_start)
        if when > end:
            continue
        value = valuer.value(Decimal(str(c["amount"])), str(c["currency"]))
        if value is None:
            unconverted += 1
            continue
        events.append((when, "expected_contribution", value, str(c["contributor"]), "expected"))

    # Within a day, outflows before inflows so the lowest point is not understated.
    events.sort(key=lambda e: (e[0], e[2] >= 0, e[1]))
    confirmed = with_expected = current
    lowest_confirmed = lowest_expected = current
    lowest_day = today
    rows = []
    for day, kind, amount, label, track in events:
        if track == "confirmed":
            confirmed += amount
        with_expected += amount
        if confirmed < lowest_confirmed:
            lowest_confirmed, lowest_day = confirmed, day
        lowest_expected = min(lowest_expected, with_expected)
        rows.append({
            "date": day.isoformat(), "kind": kind, "label": label, "amount": to_string(amount, d),
            "balance_confirmed": to_string(confirmed, d), "balance_with_expected": to_string(with_expected, d),
        })

    reserve = get_reserve(conn, workspace_id)
    floor_display = None
    if reserve is not None:
        v = valuer.value(Decimal(str(reserve["floor_amount"])), str(reserve["currency"]))
        floor_display = None if v is None else v
    return {
        "label": "forecast",
        "display_currency": d,
        "from": today.isoformat(),
        "to": end.isoformat(),
        "current_funds": to_string(current, d),
        "projected_end_confirmed": to_string(confirmed, d),
        "projected_end_with_expected": to_string(with_expected, d),
        "lowest_confirmed": to_string(lowest_confirmed, d),
        "lowest_confirmed_date": lowest_day.isoformat(),
        "lowest_with_expected": to_string(lowest_expected, d),
        "reserve_floor": None if floor_display is None else to_string(floor_display, d),
        "gap_to_floor_confirmed": None if floor_display is None else to_string(lowest_confirmed - floor_display, d),
        "gap_to_floor_with_expected": None if floor_display is None else to_string(lowest_expected - floor_display, d),
        "events": rows,
        "unconverted_count": unconverted,
        "complete": unconverted == 0,
        "valuation": valuer.policy(),
    }


def _source_outflows(
    conn: sqlite3.Connection,
    workspace_id: str,
    target_bill_id: str,
    currency: str,
    today: date,
    window_end: date,
) -> tuple[list[tuple[date, Decimal]], list[str]]:
    """Outflows that may reduce the paying account before or after the payment, in the
    source currency. Planned entries and bills carry no account, so every unattributed
    outflow is conservatively assumed to come from the paying account. The target bill
    is excluded (it is the payment itself). Returns (outflows, pairs that cannot be valued)."""
    outflows: list[tuple[date, Decimal]] = []
    missing: set[str] = set()

    def to_source(amount: Decimal, from_currency: str) -> Decimal | None:
        try:
            return rates_service.convert(amount, rates_service.get_rate(conn, workspace_id, from_currency, currency))
        except rates_service.UnsupportedPair:
            missing.add(f"{from_currency}->{currency}")
            return None

    fulfilled = fulfilled_occurrences(conn, workspace_id)
    for entry in list_entries(conn, workspace_id):
        if entry["kind"] != "expense":
            continue  # planned income is not counted as available money (conservative)
        for day in occurrences(entry, today, window_end):
            if (str(entry["id"]), day.isoformat()) in fulfilled:
                continue  # recorded as paid: already in the account balance
            value = to_source(Decimal(str(entry["amount"])), str(entry["currency"]))
            if value is not None:
                outflows.append((day, value))
    for bill in open_bills(conn, workspace_id):
        if bill["id"] == target_bill_id:
            continue
        due = max(date.fromisoformat(str(bill["due_date"])), today)
        if due > window_end:
            continue
        value = to_source(Decimal(str(bill["amount"])), str(bill["currency"]))
        if value is not None:
            outflows.append((due, value))
    return outflows, sorted(missing)


def payment_timing(
    conn: sqlite3.Connection,
    workspace_id: str,
    bill: dict[str, object],
    source_account_id: str,
    today: date,
    contribution_dates: dict[str, date] | None = None,
) -> list[dict[str, object]]:
    """For each demo route: the earliest day the payment could run under the strict reserve
    policy, and whether the estimated arrival meets the due date.

    Assumptions (returned with the result): expected contributions to the paying account
    arrive on their date and are recorded then; uncertain ones and planned income are not
    counted; planned expenses and other open bills are paid from the paying account on
    their dates. The payment is feasible on day d only if the projected balance minus the
    payment stays at or above the floor from d through the end of the window (the later of
    the due date and the last counted inflow). If an outflow cannot be valued in the
    paying account's currency, the result is "indeterminate", never a guess."""
    acct_balance = balance(conn, workspace_id, source_account_id)
    acct = next(a for a in balances(conn, workspace_id) if a["id"] == source_account_id)
    currency = acct["currency"]
    require_route_currency(currency)
    rate = rates_service.get_rate(conn, workspace_id, currency, str(bill["currency"]))
    reserve = get_reserve(conn, workspace_id)
    floor = Decimal(str(reserve["floor_amount"])) if reserve and reserve["account_id"] == source_account_id else Decimal(0)
    due = date.fromisoformat(str(bill["due_date"]))

    inflows: list[tuple[date, Decimal]] = []
    for c in list_contributions(conn, workspace_id):
        if c["status"] == "expected" and c["certainty"] == "expected" and c["account_id"] == source_account_id:
            when = (contribution_dates or {}).get(str(c["id"]), date.fromisoformat(str(c["expected_date"])))
            inflows.append((max(when, today), Decimal(str(c["amount"]))))
    window_end = max([due, today, *(when for when, _ in inflows)])
    outflows, missing = _source_outflows(conn, workspace_id, str(bill["id"]), currency, today, window_end)

    # Daily projection of the paying account. Each day's outflows come before its inflows;
    # a payment on day i is made at the end of that day.
    days = [today + timedelta(days=i) for i in range((window_end - today).days + 1)]
    out_by_day: dict[date, Decimal] = {}
    in_by_day: dict[date, Decimal] = {}
    for when, amount in outflows:
        out_by_day[when] = out_by_day.get(when, Decimal(0)) + amount
    for when, amount in inflows:
        in_by_day[when] = in_by_day.get(when, Decimal(0)) + amount
    end_of_day: list[Decimal] = []
    low_of_day: list[Decimal] = []  # after the day's outflows, before its inflows
    running = acct_balance
    for day in days:
        running -= out_by_day.get(day, Decimal(0))
        low_of_day.append(running)
        running += in_by_day.get(day, Decimal(0))
        end_of_day.append(running)
    # Lowest balance after paying on day i: that day's end, then every later day's low point.
    later_low: list[Decimal | None] = [None] * len(days)
    for i in range(len(days) - 2, -1, -1):
        nxt = low_of_day[i + 1]
        later_low[i] = nxt if later_low[i + 1] is None else min(nxt, later_low[i + 1])  # type: ignore[type-var]
    min_from = [end_of_day[i] if later_low[i] is None else min(end_of_day[i], later_low[i]) for i in range(len(days))]  # type: ignore[type-var]
    assumptions = ["contributions_recorded_on_arrival", "unattributed_outflows_from_paying_account",
                   "planned_income_not_counted"]

    results = []
    for code, route in ROUTES.items():
        needed = cost(route, Decimal(str(bill["amount"])), rate.rate, currency, today).total
        base = {"route": code, "total": to_string(needed, currency), "currency": currency, "assumptions": assumptions}
        if missing:
            results.append({**base, "status": "indeterminate", "feasible": None, "initiation_date": None,
                            "estimated_arrival": None, "on_time": None, "missing_pairs": missing})
            continue
        start_index = next((i for i in range(len(days)) if min_from[i] - needed >= floor), None)
        if start_index is None:
            results.append({**base, "status": "not_feasible", "feasible": False, "initiation_date": None,
                            "estimated_arrival": None, "on_time": False})
            continue
        start_day = days[start_index]
        c = cost(route, Decimal(str(bill["amount"])), rate.rate, currency, start_day)
        results.append({
            **base, "status": "feasible", "feasible": True, "total": to_string(c.total, currency),
            "initiation_date": start_day.isoformat(), "estimated_arrival": c.arrival.isoformat(),
            "on_time": c.arrival <= due, "balance_after": to_string(end_of_day[start_index] - c.total, currency),
        })
    return results


def run_scenario(
    conn: sqlite3.Connection, workspace_id: str, today: date, period: Period, display_currency: str, body: dict[str, object]
) -> dict[str, object]:
    """What-if calculations. Nothing is saved and no payment is authorized."""
    kind = body.get("type")
    end = max(period.end, today)
    base = project(conn, workspace_id, today, end, display_currency)
    if kind == "delay_contribution":
        contribution = get_contribution(conn, workspace_id, str(body.get("contribution_id")))
        if contribution["status"] != "expected":
            raise DomainError(409, "invalid_state", "Only an expected contribution can be delayed in a scenario.")
        new_date = parse_date(str(body.get("new_date")), "new_date")
        overrides = {str(contribution["id"]): new_date}
        # Same horizon as the baseline so the two are comparable; an inflow moved past the
        # horizon simply falls outside it. Payment timing below has its own window.
        scenario = project(conn, workspace_id, today, end, display_currency, contribution_dates=overrides)
        timing = []
        for bill in open_bills(conn, workspace_id):
            for when, routes in (("baseline", None), ("scenario", overrides)):
                timing.append({"bill_id": bill["id"], "case": when, "due_date": bill["due_date"],
                               "routes": payment_timing(conn, workspace_id, bill, str(contribution["account_id"]), today, routes)})
        return {"type": kind, "saved": False, "authorizes_payment": False, "baseline": base, "scenario": scenario,
                "payment_timing": timing, "assumption": "contribution_recorded_on_arrival"}
    if kind == "change_expense":
        entry_id = str(body.get("entry_id"))
        entry = get_entry(conn, workspace_id, entry_id)
        if entry["kind"] != "expense":
            raise DomainError(422, "invalid_entry", "Choose a planned expense.")
        new_amount = str(body.get("new_amount"))
        parse_amount(new_amount, str(entry["currency"]))
        scenario = project(conn, workspace_id, today, end, display_currency, entry_amounts={entry_id: new_amount})
        return {"type": kind, "saved": False, "authorizes_payment": False, "baseline": base, "scenario": scenario}
    raise DomainError(422, "unknown_scenario", "Choose a supported scenario type.")
