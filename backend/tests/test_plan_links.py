"""Explicitly recording a planned occurrence as paid/received (simulation clock 2026-10-19)."""

from __future__ import annotations

from .conftest import ORIGIN, balance_of, bdt_account, ok


def post(client, path, body=None):  # type: ignore[no-untyped-def]
    return client.post(path, json=body if body is not None else {}, headers=ORIGIN)


def add_expense(client, amount, start, recurrence="none", category="rent"):  # type: ignore[no-untyped-def]
    return ok(post(client, "/api/budget/entries", {"kind": "expense", "category": category, "amount": amount, "currency": "BDT",
                                                   "start_date": start, "recurrence": recurrence}))


def record(client, entry_id, occurrence_date, occurred_on="2026-10-19", account=None):  # type: ignore[no-untyped-def]
    return post(client, f"/api/budget/entries/{entry_id}/record",
                {"occurrence_date": occurrence_date, "account_id": account or bdt_account(client), "occurred_on": occurred_on})


def planned_events(client, entry_label, month="2026-10"):  # type: ignore[no-untyped-def]
    f = ok(client.get("/api/cashflow", params={"month": month, "currency": "BDT"}))
    return [e for e in f["events"] if e["kind"] == "planned_expense" and e["label"] == entry_label], f


def linked_transactions(client):  # type: ignore[no-untyped-def]
    return [t for t in ok(client.get("/api/transactions"))["transactions"] if t["source_type"] == "plan_occurrence"]


def test_recording_a_planned_expense_debits_once_and_leaves_the_forecast(sim) -> None:
    c = sim.client()
    entry = add_expense(c, "5000.00", "2026-10-21")
    before, f_before = planned_events(c, "rent")
    assert [(e["date"], e["amount"]) for e in before] == [("2026-10-21", "-5000.00")]
    result = ok(record(c, entry["id"], "2026-10-21"))
    assert result["transaction_id"]
    assert balance_of(c) == "95000.00"
    after, f_after = planned_events(c, "rent")
    assert after == []  # the fulfilled occurrence is no longer outstanding
    assert f_after["current_funds"] == "95000.00"
    # Counted once: the end of the month is unchanged (100000-5000-80000 before, 95000-80000 after).
    assert f_before["projected_end_confirmed"] == f_after["projected_end_confirmed"] == "15000.00"


def test_budget_keeps_planned_and_actual_amounts(sim) -> None:
    c = sim.client()
    entry = add_expense(c, "5000.00", "2026-10-21", category="books")
    ok(record(c, entry["id"], "2026-10-21"))
    s = ok(c.get("/api/budget/summary", params={"month": "2026-10"}))
    books = next(x for x in s["categories"] if x["category"] == "books")
    assert (books["planned"], books["actual"]) == ("6500.00", "5000.00")  # 1500 seeded + 5000 plan; 5000 actual
    item = next(i for i in s["planned_items"] if i["entry_id"] == entry["id"])
    assert item["fulfilled"] is True and item["amount"] == "5000.00"
    assert ok(c.get("/api/budget/entries"))["entries"][-1]["amount"] == "5000.00"  # plan unchanged


def test_next_recurring_occurrence_remains_outstanding(sim) -> None:
    c = sim.client()
    entry = add_expense(c, "1000.00", "2026-10-21", recurrence="monthly", category="phone")
    ok(record(c, entry["id"], "2026-10-21"))
    f = ok(c.get("/api/cashflow", params={"start": "2026-10-19", "end": "2026-12-31", "currency": "BDT"}))
    dates = [e["date"] for e in f["events"] if e["kind"] == "planned_expense" and e["amount"] == "-1000.00"]
    assert dates == ["2026-11-21", "2026-12-21"]


def test_payment_timing_does_not_count_a_recorded_outflow_twice(sim) -> None:
    c = sim.client()
    entry = add_expense(c, "5000.00", "2026-10-21")
    ok(record(c, entry["id"], "2026-10-21"))  # balance 95000
    family = ok(c.get("/api/contributions"))["contributions"][0]
    result = ok(post(c, "/api/scenarios", {"type": "delay_contribution", "contribution_id": family["id"], "new_date": "2026-10-20"}))
    a = next(r for r in next(t for t in result["payment_timing"] if t["case"] == "scenario")["routes"] if r["route"] == "A")
    # 95000 + 10000 on 10-20 - 81000 = 24000 >= 20000. Counting the rent again would leave 19000 (not feasible).
    assert (a["status"], a["initiation_date"], a["balance_after"]) == ("feasible", "2026-10-20", "24000.00")


def test_duplicate_submissions_post_once(sim) -> None:
    c = sim.client()
    entry = add_expense(c, "5000.00", "2026-10-21")
    ok(record(c, entry["id"], "2026-10-21"))
    again = record(c, entry["id"], "2026-10-21")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_recorded"
    assert len(linked_transactions(c)) == 1
    assert balance_of(c) == "95000.00"


def test_cross_workspace_and_future_posting_rejected_without_changes(sim) -> None:
    alice, bob = sim.client(), sim.client()
    entry = add_expense(alice, "5000.00", "2026-10-21")
    bob_entry = add_expense(bob, "5000.00", "2026-10-21")
    assert record(bob, entry["id"], "2026-10-21").status_code == 404  # alice's plan
    assert record(bob, bob_entry["id"], "2026-10-21", account=bdt_account(alice)).status_code == 404  # alice's account
    future = record(alice, entry["id"], "2026-10-21", occurred_on="2026-10-21")
    assert future.status_code == 422 and future.json()["error"]["code"] == "future_date"
    wrong_day = record(alice, entry["id"], "2026-10-22")
    assert wrong_day.status_code == 422 and wrong_day.json()["error"]["code"] == "not_an_occurrence"
    for client in (alice, bob):
        assert balance_of(client) == "100000.00"
        assert linked_transactions(client) == []
    still, _ = planned_events(alice, "rent")
    assert [e["date"] for e in still] == ["2026-10-21"]


def test_independent_transactions_are_not_matched_to_plans(sim) -> None:
    c = sim.client()
    add_expense(c, "5000.00", "2026-10-21")
    ok(post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "expense", "category": "rent",
                                     "amount": "5000.00", "occurred_on": "2026-10-19"}))
    events, _ = planned_events(c, "rent")
    assert [e["date"] for e in events] == ["2026-10-21"]  # same amount and category, still not linked


def test_concurrent_submissions_post_once(sim) -> None:
    import threading
    from datetime import date

    from app.errors import DomainError
    from app.services import budget

    c = sim.client()
    entry = add_expense(c, "5000.00", "2026-10-21")
    workspace_id, account = ok(c.get("/api/session"))["workspace_id"], bdt_account(c)
    outcomes: list[str] = []
    barrier = threading.Barrier(6)

    def worker() -> None:
        barrier.wait()
        try:
            with sim.db.transaction() as conn:
                budget.record_occurrence(conn, workspace_id, entry["id"], date(2026, 10, 21), account, date(2026, 10, 19),
                                         date(2026, 10, 19), sim.clock.now())
            outcomes.append("posted")
        except DomainError as exc:
            outcomes.append(exc.code)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["already_recorded"] * 5 + ["posted"]
    assert len(linked_transactions(c)) == 1 and balance_of(c) == "95000.00"
