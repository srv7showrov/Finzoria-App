"""Stage B / Prompt 2: shared financial services, budgets, currency and scenarios.
All figures use the demo fixed scenario under a 2026-10-19 simulation clock."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.budget import occurrences

from .conftest import ORIGIN, balance_of, bdt_account, ok


def post(client, path, body):  # type: ignore[no-untyped-def]
    return client.post(path, json=body, headers=ORIGIN)


def test_seeded_fixture_scenario(sim) -> None:
    c = sim.client()
    assert balance_of(c) == "100000.00"
    reserve = ok(c.get("/api/reserve"))["reserve"]
    assert (reserve["floor_amount"], reserve["currency"], reserve["headroom"]) == ("20000.00", "BDT", "80000.00")
    bill = ok(c.get("/api/bills"))["bills"][0]
    assert (bill["amount"], bill["currency"], bill["due_date"], bill["status"]) == ("1000.00", "AUD", "2026-10-25", "open")
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    assert (contribution["amount"], contribution["expected_date"], contribution["status"]) == ("10000.00", "2026-10-20", "expected")
    snapshots = ok(c.get("/api/rates"))["snapshots"]
    bdt_aud = next(s for s in snapshots if (s["base"], s["quote"]) == ("BDT", "AUD"))
    assert (bdt_aud["rate"], bdt_aud["mode"]) == ("0.0125", "fixture")
    assert "not market data" in bdt_aud["source"]


def test_arithmetic_fixture_monthly_remainder(sim) -> None:
    c = sim.client()
    s = ok(c.get("/api/budget/summary", params={"month": "2026-10"}))
    assert (s["planned_income"], s["planned_expenses"], s["planned_remainder"]) == ("45000.00", "32500.00", "12500.00")
    assert s["display_currency"] == "BDT" and s["complete"] is True
    # The dashboard uses the same service and therefore the same figures.
    d = ok(c.get("/api/dashboard", params={"month": "2026-10"}))
    assert d["budget"]["planned_remainder"] == "12500.00"


def test_mixed_currency_fixture_and_unsupported_pair(sim) -> None:
    c = sim.client()
    for amount, currency in (("100.00", "AUD"), ("20.00", "USD")):
        ok(post(c, "/api/budget/entries", {"kind": "expense", "category": "books", "amount": amount, "currency": currency,
                                           "start_date": "2026-09-15", "recurrence": "none"}))
    s = ok(c.get("/api/budget/summary", params={"start": "2026-09-01", "end": "2026-09-30", "currency": "AUD"}))
    assert s["planned_expenses"] == "130.00"
    originals = sorted((i["amount"], i["currency"]) for i in s["planned_items"])
    assert originals == [("100.00", "AUD"), ("20.00", "USD")]  # originals preserved

    ok(post(c, "/api/budget/entries", {"kind": "expense", "category": "books", "amount": "50.00", "currency": "EUR",
                                       "start_date": "2026-09-16", "recurrence": "none"}))
    s = ok(c.get("/api/budget/summary", params={"start": "2026-09-01", "end": "2026-09-30", "currency": "AUD"}))
    assert s["planned_expenses"] == "130.00"  # EUR is not silently converted at 1
    assert s["unconverted_count"] == 1 and s["complete"] is False
    assert "EUR->AUD" in s["valuation"]["missing_pairs"]
    eur = next(i for i in s["planned_items"] if i["currency"] == "EUR")
    assert eur["display_amount"] is None


def test_conversion_rules(sim) -> None:
    c = sim.client()
    same = ok(c.get("/api/rates/convert", params={"amount": "123.45", "from": "BDT", "to": "BDT"}))
    assert (same["result"], same["rate"]["rate"], same["rate"]["mode"]) == ("123.45", "1", "identity")
    inverse = ok(c.get("/api/rates/convert", params={"amount": "1000", "from": "AUD", "to": "BDT"}))
    assert (inverse["result"], inverse["rate"]["derived"]) == ("80000.00", True)
    missing = c.get("/api/rates/convert", params={"amount": "10", "from": "EUR", "to": "JPY"})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "unsupported_pair"
    jpy = ok(post(c, "/api/rates/manual", {"base": "AUD", "quote": "JPY", "rate": "99.5"}))
    assert jpy["id"]
    rounded = ok(c.get("/api/rates/convert", params={"amount": "10.01", "from": "AUD", "to": "JPY"}))
    assert rounded["result"] == "996"  # 995.995 rounded once to JPY's 0 decimals (half-even)


@pytest.mark.parametrize("rate", ["0", "-1", "1e3", "NaN", "Infinity", "abc"])
def test_invalid_rates_rejected(sim, rate: str) -> None:
    c = sim.client()
    response = post(c, "/api/rates/manual", {"base": "EUR", "quote": "AUD", "rate": rate})
    assert response.status_code == 422


def test_numbers_instead_of_decimal_strings_rejected(sim) -> None:
    c = sim.client()
    assert post(c, "/api/rates/manual", {"base": "EUR", "quote": "AUD", "rate": 1.65}).status_code == 422
    assert post(c, "/api/budget/entries", {"kind": "expense", "category": "food", "amount": 10.5, "currency": "BDT",
                                           "start_date": "2026-10-01", "recurrence": "none"}).status_code == 422


def test_manual_rate_takes_effect_with_provenance(sim) -> None:
    c = sim.client()
    sim.clock.advance(minutes=1)
    ok(post(c, "/api/rates/manual", {"base": "BDT", "quote": "AUD", "rate": "0.0124"}))
    r = ok(c.get("/api/rates/convert", params={"amount": "80000", "from": "BDT", "to": "AUD"}))
    assert (r["result"], r["rate"]["mode"]) == ("992.00", "manual")
    snapshots = ok(c.get("/api/rates"))["snapshots"]
    current = [s for s in snapshots if (s["base"], s["quote"]) == ("BDT", "AUD")]
    assert [s["current"] for s in current] == [True, False]  # history kept, newest is current


def test_month_end_recurrence_rule() -> None:
    entry = {"start_date": "2026-01-31", "recurrence": "monthly", "end_date": None}
    days = occurrences(entry, date(2026, 1, 1), date(2026, 5, 31))
    assert days == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31)]
    leap = occurrences({"start_date": "2028-01-30", "recurrence": "monthly", "end_date": "2028-03-29"}, date(2028, 1, 1), date(2028, 12, 31))
    assert leap == [date(2028, 1, 30), date(2028, 2, 29)]
    once = occurrences({"start_date": "2026-10-05", "recurrence": "none", "end_date": None}, date(2026, 10, 1), date(2026, 10, 31))
    assert once == [date(2026, 10, 5)]


def test_month_end_recurrence_via_api(sim) -> None:
    c = sim.client()
    ok(post(c, "/api/budget/entries", {"kind": "expense", "category": "rent", "amount": "700.00", "currency": "AUD",
                                       "start_date": "2027-01-31", "recurrence": "monthly"}))
    feb = ok(c.get("/api/budget/summary", params={"month": "2027-02", "currency": "AUD"}))
    rent = [i for i in feb["planned_items"] if i["currency"] == "AUD"]
    assert [(i["date"], i["amount"]) for i in rent] == [("2027-02-28", "700.00")]


@pytest.mark.parametrize(
    "params",
    [{"start": "2026-10-10", "end": "2026-10-01"}, {"start": "2026-01-01", "end": "2027-06-01"},
     {"start": "2026-10-01"}, {"month": "2026-13"}],
)
def test_invalid_periods_rejected(sim, params) -> None:
    c = sim.client()
    assert c.get("/api/budget/summary", params=params).status_code == 422


def test_receiving_contribution_credits_exactly_once(sim) -> None:
    c = sim.client()
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    first = ok(post(c, f"/api/contributions/{contribution['id']}/receive", {}))
    second = ok(post(c, f"/api/contributions/{contribution['id']}/receive", {}))
    assert (first["credited"], second["credited"]) == (True, False)
    assert balance_of(c) == "110000.00"
    credits = [t for t in ok(c.get("/api/transactions"))["transactions"] if t["kind"] == "contribution"]
    assert len(credits) == 1 and credits[0]["amount"] == "10000.00"
    # Once received it is actual money, no longer an expected inflow in forecasts.
    assert ok(c.get("/api/dashboard"))["funding"]["expected_contributions"] == "0.00"


def test_contribution_cannot_be_received_in_the_future(sim) -> None:
    c = sim.client()
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    response = post(c, f"/api/contributions/{contribution['id']}/receive", {"received_on": "2026-10-21"})
    assert response.status_code == 422
    assert balance_of(c) == "100000.00"


def test_forecast_separates_actual_expected_and_uncertain(sim) -> None:
    c = sim.client()
    ok(post(c, "/api/contributions", {"account_id": bdt_account(c), "contributor": "Scholarship (maybe)", "amount": "5000.00",
                                      "expected_date": "2026-10-22", "certainty": "uncertain"}))
    d = ok(c.get("/api/dashboard", params={"month": "2026-10"}))
    assert d["balances"][0]["balance"] == "100000.00"  # expected money is not available cash
    f = ok(c.get("/api/cashflow", params={"month": "2026-10", "currency": "BDT"}))
    assert f["label"] == "forecast"
    # Rest of October: tuition AUD 1000 = BDT 80000 on the 25th; monthly entries start Nov 1 (outside range).
    assert f["current_funds"] == "100000.00"  # BDT 100000 + AUD 0
    bdt_only = [e for e in f["events"] if e["kind"] == "bill"]
    assert [(e["date"], e["amount"]) for e in bdt_only] == [("2026-10-25", "-80000.00")]
    expected = [e for e in f["events"] if e["kind"] == "expected_contribution"]
    assert [(e["date"], e["amount"]) for e in expected] == [("2026-10-20", "10000.00")]  # uncertain one excluded
    assert d["funding"]["uncertain_contributions_excluded"] == "5000.00"
    assert d["funding"]["expected_contributions"] == "10000.00"


def test_delayed_contribution_scenario_matches_fixture_and_saves_nothing(sim) -> None:
    c = sim.client()
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    result = ok(post(c, "/api/scenarios", {"type": "delay_contribution", "contribution_id": contribution["id"],
                                          "new_date": "2026-10-24"}))
    assert result["saved"] is False and result["authorizes_payment"] is False
    timing = {t["case"]: {r["route"]: r for r in t["routes"]} for t in result["payment_timing"]}
    base, delayed = timing["baseline"], timing["scenario"]
    assert (base["A"]["initiation_date"], base["A"]["estimated_arrival"], base["A"]["on_time"]) == ("2026-10-20", "2026-10-22", True)
    assert (delayed["A"]["estimated_arrival"], delayed["A"]["on_time"]) == ("2026-10-26", False)
    assert (delayed["B"]["estimated_arrival"], delayed["B"]["on_time"]) == ("2026-10-25", True)
    assert (delayed["C"]["estimated_arrival"], delayed["C"]["on_time"]) == ("2026-11-01", False)
    assert delayed["A"]["balance_after"] == "29000.00"
    # Nothing changed.
    assert ok(c.get("/api/contributions"))["contributions"][0]["expected_date"] == "2026-10-20"
    assert balance_of(c) == "100000.00"
    assert ok(c.get("/api/bills"))["bills"][0]["status"] == "open"


def test_expense_change_scenario_does_not_mutate(sim) -> None:
    c = sim.client()
    rent = next(e for e in ok(c.get("/api/budget/entries"))["entries"] if e["category"] == "rent")
    result = ok(post(c, "/api/scenarios?month=2026-11", {"type": "change_expense", "entry_id": rent["id"], "new_amount": "15000.00"}))
    before = result["baseline"]["projected_end_confirmed"]
    after = result["scenario"]["projected_end_confirmed"]
    from decimal import Decimal

    assert Decimal(before) - Decimal(after) == Decimal("5000.00")  # one November rent occurrence
    assert next(e for e in ok(c.get("/api/budget/entries"))["entries"] if e["id"] == rent["id"])["amount"] == "10000.00"


def test_display_currency_switch_preserves_originals(sim) -> None:
    c = sim.client()
    c.put("/api/preferences", json={"language": "en", "display_currency": "AUD", "time_zone": "Asia/Dhaka"}, headers=ORIGIN).raise_for_status()
    s = ok(c.get("/api/budget/summary", params={"month": "2026-10"}))
    assert s["display_currency"] == "AUD"
    assert (s["planned_income"], s["planned_remainder"]) == ("562.50", "156.25")
    assert {e["amount"] for e in ok(c.get("/api/budget/entries"))["entries"]} >= {"45000.00", "10000.00"}
    assert balance_of(c) == "100000.00"


def test_actual_versus_planned(sim) -> None:
    c = sim.client()
    ok(post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "expense", "category": "food",
                                     "amount": "3000.00", "occurred_on": "2026-10-19"}))
    s = ok(c.get("/api/budget/summary", params={"month": "2026-10"}))
    food = next(x for x in s["categories"] if x["category"] == "food")
    assert (food["planned"], food["actual"], food["difference"]) == ("12000.00", "3000.00", "9000.00")
    assert s["actual_expenses"] == "3000.00"
    assert balance_of(c) == "97000.00"


def test_rate_targets_are_checked_on_refresh(sim) -> None:
    c = sim.client()
    ok(post(c, "/api/rates/targets", {"base": "BDT", "quote": "AUD", "threshold": "0.0125", "direction": "at_or_above"}))
    targets = ok(post(c, "/api/rates/targets", {"base": "BDT", "quote": "AUD", "threshold": "0.013", "direction": "at_or_above"}))["targets"]
    assert [t["met"] for t in targets] == [True, False]
    assert {t["check_mode"] for t in targets} == {"on_refresh"}


def test_rate_change_scenario(sim) -> None:
    c = sim.client()
    r = ok(post(c, "/api/rates/scenario", {"base": "AUD", "quote": "BDT", "amount": "1000.00", "change_percent": "5"}))
    assert (r["current_value"], r["scenario_value"], r["difference"], r["saved"]) == ("80000.00", "84000.00", "4000.00", False)


def test_finance_records_are_workspace_scoped(sim) -> None:
    alice, bob = sim.client(), sim.client()
    contribution = ok(alice.get("/api/contributions"))["contributions"][0]
    entry = ok(alice.get("/api/budget/entries"))["entries"][0]
    assert post(bob, f"/api/contributions/{contribution['id']}/receive", {}).status_code == 404
    assert bob.delete(f"/api/budget/entries/{entry['id']}", headers=ORIGIN).status_code == 404
    assert post(bob, "/api/transactions", {"account_id": bdt_account(alice), "kind": "expense", "category": "food",
                                           "amount": "1.00", "occurred_on": "2026-10-19"}).status_code == 404
    assert post(bob, "/api/reserve", {}).status_code in (404, 405)
    assert bob.put("/api/reserve", json={"account_id": bdt_account(alice), "floor_amount": "1.00"}, headers=ORIGIN).status_code == 404
    assert post(bob, "/api/scenarios", {"type": "delay_contribution", "contribution_id": contribution["id"],
                                        "new_date": "2026-10-24"}).status_code == 404
    assert balance_of(alice) == "100000.00"
    assert ok(alice.get("/api/contributions"))["contributions"][0]["status"] == "expected"
