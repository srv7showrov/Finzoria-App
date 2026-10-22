"""Proposals for a bill that another payment already settled (owner's Windows review finding).

Funds are raised first so that every remaining check (funds, reserve, quote) would pass: the
rejections below can only come from the settled bill, not from insufficient funds."""

from __future__ import annotations

from .conftest import ORIGIN, balance_of, bdt_account, ok
from .test_payments import approve, execute, payment_transactions, post, propose, tuition


def add_income(client, amount: str = "200000.00") -> None:  # type: ignore[no-untyped-def]
    ok(post(client, "/api/transactions", {"account_id": bdt_account(client), "kind": "income", "category": "income",
                                          "description": "Scholarship (fictional)", "amount": amount, "occurred_on": "2026-10-19"}))


def error_code(response) -> str:  # type: ignore[no-untyped-def]
    return str(response.json()["error"]["code"])


def test_other_open_proposal_becomes_unavailable_when_bill_is_settled(sim) -> None:
    c = sim.client()
    add_income(c)
    first, second = propose(c, "A"), propose(c, "C")
    assert first["checks"]["blocking"] == [] and second["checks"]["blocking"] == []
    ok(approve(c, first))
    receipt = ok(execute(c, first))
    assert tuition(c)["status"] == "settled"
    after_first = balance_of(c)
    assert after_first == "219000.00"  # 300,000 - 81,000

    # Listed and opened as unavailable because the bill is settled; terms kept as history.
    listed = next(p for p in ok(c.get("/api/payments/proposals"))["proposals"] if p["id"] == second["id"])
    opened = ok(c.get(f"/api/payments/proposals/{second['id']}"))
    for view in (listed, opened):
        assert (view["status"], view["status_reason"], view["checks"]) == ("cancelled", "bill_settled", None)
        assert view["terms"] == second["terms"] and view["terms_hash"] == second["terms_hash"]

    # Enough money remains for the second route (80,500 + 20,000 floor < 219,000), yet the server refuses.
    assert int(after_first.split(".")[0]) > 80500 + 20000
    rejected = approve(c, second)
    assert rejected.status_code == 409 and error_code(rejected) == "bill_settled"
    rejected = execute(c, second, key="exec-key-0002")
    assert rejected.status_code == 409 and error_code(rejected) == "bill_settled"
    rejected = post(c, f"/api/payments/proposals/{second['id']}/refresh")
    assert rejected.status_code == 409 and error_code(rejected) == "bill_settled"

    # Nothing else moved; the executed payment and its receipt are intact.
    assert balance_of(c) == after_first
    assert len(payment_transactions(c)) == 2  # one payment + one fee
    executions = ok(c.get("/api/payments/executions"))["executions"]
    assert [e["execution_id"] for e in executions] == [receipt["execution_id"]]
    assert ok(c.get(f"/api/payments/executions/{receipt['execution_id']}"))["receipt_number"] == receipt["receipt_number"]
    events = ok(c.get("/api/activity"))["events"]
    assert any(e["event_type"] == "payment_cancelled" and e["entity_id"] == second["id"]
               and e["details"].get("reason") == "bill_settled" for e in events)


def test_approved_sibling_cannot_run_after_bill_settled(sim) -> None:
    c = sim.client()
    add_income(c)
    first, second = propose(c, "A"), propose(c, "B")
    ok(approve(c, first))
    ok(approve(c, second))
    ok(execute(c, first))
    balance = balance_of(c)
    rejected = execute(c, second, key="exec-key-0003")
    assert rejected.status_code == 409 and error_code(rejected) == "bill_settled"
    assert balance_of(c) == balance and len(payment_transactions(c)) == 2
    view = ok(c.get(f"/api/payments/proposals/{second['id']}"))
    assert (view["status"], view["status_reason"]) == ("cancelled", "bill_settled")


def test_proposal_left_open_before_this_fix_is_reported_and_refused(sim) -> None:
    """Workspaces created before siblings were closed at execution can still hold an open
    proposal for a settled bill. It is shown as unavailable and refused, with funds available."""
    c = sim.client()
    add_income(c)
    first, second = propose(c, "A"), propose(c, "C")
    ok(approve(c, first))
    ok(execute(c, first))
    with sim.db.transaction() as conn:  # recreate the earlier state: still 'ready_for_review'
        conn.execute("UPDATE payment_proposals SET status = 'ready_for_review', status_reason = NULL WHERE id = ?",
                     (second["id"],))
    view = ok(c.get(f"/api/payments/proposals/{second['id']}"))
    assert (view["status"], view["status_reason"]) == ("cancelled", "bill_settled")
    rejected = c.post(f"/api/payments/proposals/{second['id']}/approve",
                      json={"version": second["version"], "terms_hash": second["terms_hash"]}, headers=ORIGIN)
    assert rejected.status_code == 409 and error_code(rejected) == "bill_settled"
    assert len(payment_transactions(c)) == 2
