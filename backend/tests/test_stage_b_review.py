"""Regression tests for four independently reproduced Stage B issues (2026-10-19 review).
Simulation clock: 2026-10-19 09:00 Asia/Dhaka."""

from __future__ import annotations

from .conftest import ORIGIN, balance_of, bdt_account, ok


def post(client, path, body=None):  # type: ignore[no-untyped-def]
    return client.post(path, json=body if body is not None else {}, headers=ORIGIN)


def add_entry(client, kind, amount, on, currency="BDT", category="rent"):  # type: ignore[no-untyped-def]
    return ok(post(client, "/api/budget/entries", {"kind": kind, "category": category if kind == "expense" else "income",
                                                   "amount": amount, "currency": currency, "start_date": on, "recurrence": "none"}))


def family(client):  # type: ignore[no-untyped-def]
    return ok(client.get("/api/contributions"))["contributions"][0]


# 1. Future-dated actual transactions -------------------------------------------------


def test_future_dated_actual_transaction_rejected_without_side_effects(sim) -> None:
    c = sim.client()
    before = ok(c.get("/api/transactions"))["transactions"]
    response = post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "income", "category": "income",
                                             "amount": "10000.00", "occurred_on": "2026-10-24"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "future_date"
    assert balance_of(c) == "100000.00"
    assert ok(c.get("/api/transactions"))["transactions"] == before
    # Today (workspace time zone) is still allowed.
    ok(post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "income", "category": "income",
                                     "amount": "10.00", "occurred_on": "2026-10-19"}))
    assert balance_of(c) == "100010.00"


# 2. Today's outstanding planned cash flow -----------------------------------------------


def test_items_due_today_are_projected_today(sim) -> None:
    c = sim.client()
    add_entry(c, "expense", "50000.00", "2026-10-19")
    ok(post(c, "/api/bills", {"description": "Library fine (demo)", "payee": "Example University (fictional)",
                              "category": "campus", "amount": "100.00", "currency": "AUD", "due_date": "2026-10-19"}))
    ok(post(c, "/api/contributions", {"account_id": bdt_account(c), "contributor": "Aunt (demo)", "amount": "2000.00",
                                      "expected_date": "2026-10-19", "certainty": "expected"}))
    f = ok(c.get("/api/cashflow", params={"month": "2026-10", "currency": "BDT"}))
    today = {(e["kind"], e["amount"]) for e in f["events"] if e["date"] == "2026-10-19"}
    assert ("planned_expense", "-50000.00") in today
    assert ("bill", "-8000.00") in today
    assert ("expected_contribution", "2000.00") in today
    # Actual funds are unchanged; expected money is only in the "with expected" line.
    assert f["current_funds"] == "100000.00" and balance_of(c) == "100000.00"
    # 100000 - 50000 - 8000 (fine) - 80000 (tuition 10-25) = -38000; + 2000 + 10000 expected = -26000.
    assert f["projected_end_confirmed"] == "-38000.00"
    assert f["projected_end_with_expected"] == "-26000.00"


# 3. Payment timing must count intervening outflows ---------------------------------------


def timing(result, case):  # type: ignore[no-untyped-def]
    entry = next(t for t in result["payment_timing"] if t["case"] == case)
    return {r["route"]: r for r in entry["routes"]}


def test_payment_timing_counts_intervening_outflows(sim) -> None:
    c = sim.client()
    add_entry(c, "expense", "50000.00", "2026-10-21")
    result = ok(post(c, "/api/scenarios", {"type": "delay_contribution", "contribution_id": family(c)["id"], "new_date": "2026-10-24"}))
    a = timing(result, "scenario")["A"]
    # 100000 - 50000 rent + 10000 (10-24) = 60000 < 81000 + 20000 floor: not feasible.
    assert a["feasible"] is False and a["status"] == "not_feasible"
    assert a.get("balance_after") != "29000.00"
    assert timing(result, "baseline")["A"]["feasible"] is False


def test_payment_timing_indeterminate_when_outflow_cannot_be_valued(sim) -> None:
    c = sim.client()
    add_entry(c, "expense", "300.00", "2026-10-22", currency="EUR")  # no EUR rate exists
    result = ok(post(c, "/api/scenarios", {"type": "delay_contribution", "contribution_id": family(c)["id"], "new_date": "2026-10-24"}))
    a = timing(result, "scenario")["A"]
    assert a["status"] == "indeterminate" and a["feasible"] is None


def test_original_delay_fixture_preserved(sim) -> None:
    c = sim.client()
    result = ok(post(c, "/api/scenarios", {"type": "delay_contribution", "contribution_id": family(c)["id"], "new_date": "2026-10-24"}))
    s, b = timing(result, "scenario"), timing(result, "baseline")
    assert (s["A"]["estimated_arrival"], s["A"]["on_time"], s["A"]["balance_after"]) == ("2026-10-26", False, "29000.00")
    assert (s["B"]["estimated_arrival"], s["B"]["on_time"]) == ("2026-10-25", True)
    assert (b["A"]["initiation_date"], b["A"]["estimated_arrival"]) == ("2026-10-20", "2026-10-22")


# 4. Baseline and scenario use the same horizon ------------------------------------------


def test_delay_scenario_keeps_selected_horizon(sim) -> None:
    c = sim.client()
    result = ok(post(c, "/api/scenarios?month=2026-10", {"type": "delay_contribution", "contribution_id": family(c)["id"],
                                                          "new_date": "2026-11-10"}))
    base, scen = result["baseline"], result["scenario"]
    assert (base["from"], base["to"]) == (scen["from"], scen["to"]) == ("2026-10-19", "2026-10-31")
    # The delayed inflow falls outside the selected horizon.
    assert scen["projected_end_with_expected"] == scen["projected_end_confirmed"] == "20000.00"
    assert base["projected_end_with_expected"] == "30000.00"
