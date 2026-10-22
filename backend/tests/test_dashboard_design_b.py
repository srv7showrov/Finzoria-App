"""Design B dashboard fields: category breakdown and account-specific reserve percentages.
Both are derived in the dashboard service from the shared budget and reserve services."""

from __future__ import annotations

from decimal import Decimal

from app.services.dashboard import percent

from .conftest import ORIGIN, bdt_account, ok


def test_percent_rounds_half_even_and_rejects_non_positive_whole() -> None:
    assert percent(Decimal("1"), Decimal("8")) == "12"  # 12.5 -> 12 (half-even)
    assert percent(Decimal("3"), Decimal("8")) == "38"  # 37.5 -> 38
    assert percent(Decimal("5"), Decimal("0")) is None
    assert percent(Decimal("5"), Decimal("-1")) is None


def test_dashboard_categories_are_planned_shares_with_actual_kept_separate(sim) -> None:
    c = sim.client()
    d = ok(c.get("/api/dashboard", params={"month": "2026-10"}))
    rows = [(x["category"], x["planned"], x["actual"], x["planned_share_percent"]) for x in d["categories"]]
    # 32500 planned: food 12000 (36.9 %), rent 10000 (30.8 %), transport 6500 (20 %), phone 2500 (7.7 %), books 1500 (4.6 %).
    assert rows == [
        ("food", "12000.00", "0.00", "37"),
        ("rent", "10000.00", "0.00", "31"),
        ("transport", "6500.00", "0.00", "20"),
        ("phone", "2500.00", "0.00", "8"),
        ("books", "1500.00", "0.00", "5"),
    ]
    # Same figures as the budget summary (one service).
    s = ok(c.get("/api/budget/summary", params={"month": "2026-10"}))
    assert {x["category"]: x["planned"] for x in s["categories"]} == {x["category"]: x["planned"] for x in d["categories"]}

    # Actual spending appears beside the plan and does not change the planned share.
    ok(c.post("/api/transactions", json={"account_id": bdt_account(c), "kind": "expense", "category": "food",
                                         "description": "Groceries", "amount": "600.00", "occurred_on": "2026-10-18"}, headers=ORIGIN))
    d = ok(c.get("/api/dashboard", params={"month": "2026-10"}))
    food = next(x for x in d["categories"] if x["category"] == "food")
    assert (food["planned"], food["actual"], food["planned_share_percent"]) == ("12000.00", "600.00", "37")

    # Display currency converts the view only; shares are unchanged.
    aud = ok(c.get("/api/dashboard", params={"month": "2026-10", "currency": "AUD"}))
    assert [x["planned_share_percent"] for x in aud["categories"]] == ["37", "31", "20", "8", "5"]
    assert next(x for x in aud["categories"] if x["category"] == "food")["planned"] == "150.00"


def test_dashboard_category_share_is_none_without_planned_spending(sim) -> None:
    c = sim.client()
    ok(c.post("/api/transactions", json={"account_id": bdt_account(c), "kind": "expense", "category": "health",
                                         "description": "Pharmacy", "amount": "300.00", "occurred_on": "2026-09-10"}, headers=ORIGIN))
    d = ok(c.get("/api/dashboard", params={"month": "2026-09"}))
    assert d["budget"]["planned_expenses"] == "0.00"
    assert [(x["category"], x["actual"], x["planned_share_percent"]) for x in d["categories"]] == [("health", "300.00", None)]


def test_dashboard_reserve_percentages_are_of_the_reserve_account_only(sim) -> None:
    c = sim.client()
    r = ok(c.get("/api/dashboard"))["reserve"]
    assert (r["currency"], r["floor_amount"], r["headroom"]) == ("BDT", "20000.00", "80000.00")
    assert (r["floor_percent"], r["headroom_percent"]) == ("20", "80")
    # Converting the view to AUD does not change the account-specific reserve (still BDT).
    r_aud = ok(c.get("/api/dashboard", params={"currency": "AUD"}))["reserve"]
    assert (r_aud["currency"], r_aud["floor_amount"], r_aud["floor_percent"]) == ("BDT", "20000.00", "20")
