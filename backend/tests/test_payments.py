"""Stage B / Prompt 3: reviewed, explicitly approved, SIMULATED payments.
demo fixture under the 2026-10-19 simulation clock."""

from __future__ import annotations

import threading

import pytest

from app.services import payments as payments_service

from .conftest import ORIGIN, balance_of, bdt_account, ok


def post(client, path, body=None):  # type: ignore[no-untyped-def]
    return client.post(path, json=body if body is not None else {}, headers=ORIGIN)


def tuition(client) -> dict:  # type: ignore[no-untyped-def,type-arg]
    return ok(client.get("/api/bills"))["bills"][0]


def propose(client, route: str = "A") -> dict:  # type: ignore[no-untyped-def,type-arg]
    return ok(post(client, "/api/payments/proposals",
                   {"bill_id": tuition(client)["id"], "source_account_id": bdt_account(client), "route": route}))


def approve(client, proposal):  # type: ignore[no-untyped-def]
    return post(client, f"/api/payments/proposals/{proposal['id']}/approve",
                {"version": proposal["version"], "terms_hash": proposal["terms_hash"]})


def execute(client, proposal, key: str = "exec-key-0001"):  # type: ignore[no-untyped-def]
    return post(client, f"/api/payments/proposals/{proposal['id']}/execute", {"idempotency_key": key})


def receive_family(client) -> None:  # type: ignore[no-untyped-def]
    contribution = ok(client.get("/api/contributions"))["contributions"][0]
    ok(post(client, f"/api/contributions/{contribution['id']}/receive"))


def payment_transactions(client) -> list:  # type: ignore[no-untyped-def,type-arg]
    return [t for t in ok(client.get("/api/transactions"))["transactions"] if t["kind"] in ("payment", "fee")]


def test_route_comparison_matches_fixture(sim) -> None:
    c = sim.client()
    routes = ok(c.get(f"/api/bills/{tuition(c)['id']}/routes", params={"source_account_id": bdt_account(c)}))
    by = {r["route"]: r for r in routes["routes"]}
    assert routes["rate"]["rate"] == "0.0125" and routes["rate"]["mode"] == "fixture"
    assert routes["objective"]["reserve_floor"] == "20000.00"
    assert (by["A"]["principal"], by["A"]["fee"], by["A"]["total_debit"]) == ("80000.00", "1000.00", "81000.00")
    assert (by["A"]["balance_after"], by["A"]["gap_to_floor"], by["A"]["reserve_ok"]) == ("19000.00", "-1000.00", False)
    assert (by["B"]["total_debit"], by["B"]["reserve_ok"], by["B"]["estimated_arrival"]) == ("81500.00", False, "2026-10-20")
    assert (by["C"]["total_debit"], by["C"]["estimated_arrival"], by["C"]["on_time"]) == ("80500.00", "2026-10-27", False)
    assert by["A"]["estimated_arrival"] == "2026-10-21" and by["A"]["on_time"] is True
    assert all(r["fictional"] for r in routes["routes"])


def test_full_fixture_flow(sim) -> None:
    c = sim.client()
    # 1. Payment A is prepared but blocked by the reserve floor today.
    proposal = propose(c, "A")
    assert proposal["status"] == "ready_for_review" and proposal["simulated"] is True
    assert proposal["terms"]["total_debit"] == "81000.00"
    assert proposal["checks"]["balance_after"] == "19000.00"
    assert proposal["checks"]["blocking"] == ["reserve_breach"]
    blocked = approve(c, proposal)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "reserve_breach"
    assert execute(c, proposal).json()["error"]["code"] == "not_approved"
    assert balance_of(c) == "100000.00" and payment_transactions(c) == []

    # 2. The contribution is received once: BDT 110000.
    receive_family(c)
    receive_family(c)
    assert balance_of(c) == "110000.00"

    # 3. Explicit approval of the exact version reviewed, then simulated execution.
    reviewed = ok(c.get(f"/api/payments/proposals/{proposal['id']}"))
    assert reviewed["checks"]["blocking"] == [] and reviewed["checks"]["balance_after"] == "29000.00"
    approved = ok(approve(c, reviewed))
    assert approved["status"] == "approved" and approved["approved_version"] == 1
    result = ok(execute(c, approved, "fixture-run-0001"))
    assert result["status"] == "executed_simulated" and result["simulated"] is True and result["replayed"] is False
    assert (result["total_debit"], result["balance_before"], result["balance_after"]) == ("81000.00", "110000.00", "29000.00")
    assert result["receipt_number"].startswith("SIM-")
    assert balance_of(c) == "29000.00"

    # 4. Retries (same key, new key) return the first result; nothing changes.
    again = ok(execute(c, approved, "fixture-run-0001"))
    other_key = ok(execute(c, approved, "fixture-run-0002"))
    assert again["execution_id"] == other_key["execution_id"] == result["execution_id"]
    assert again["replayed"] is other_key["replayed"] is True
    assert balance_of(c) == "29000.00"
    assert sorted((t["kind"], t["amount"]) for t in payment_transactions(c)) == [("fee", "1000.00"), ("payment", "80000.00")]
    bill = tuition(c)
    assert (bill["status"], bill["settled_by_execution_id"]) == ("settled", result["execution_id"])
    assert len(ok(c.get("/api/payments/executions"))["executions"]) == 1

    # Settled bill no longer counts as a future deduction; spending shows in actuals.
    dashboard = ok(c.get("/api/dashboard", params={"month": "2026-10"}))
    assert dashboard["upcoming_bills"] == []
    assert dashboard["budget"]["actual_expenses"] == "81000.00"
    assert ok(c.get("/api/budget/summary", params={"month": "2026-10"}))["actual_income"] == "10000.00"


def test_status_lookup_and_receipt(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = ok(approve(c, propose(c, "A")))
    assert ok(c.get("/api/payments/executions/status", params={"idempotency_key": "lookup-key-01"})) == {
        "found": False, "idempotency_key": "lookup-key-01"}
    result = ok(execute(c, proposal, "lookup-key-01"))
    status = ok(c.get("/api/payments/executions/status", params={"idempotency_key": "lookup-key-01"}))
    assert status["found"] is True and status["result"]["execution_id"] == result["execution_id"]
    receipt = ok(c.get(f"/api/payments/executions/{result['execution_id']}"))
    assert receipt["simulated"] is True and receipt["recipient_amount"] == "1000.00" and receipt["refunds"] == []


def test_concurrent_execution_debits_once(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = ok(approve(c, propose(c, "A")))
    workspace_id = ok(c.get("/api/session"))["workspace_id"]
    results: list[object] = []
    barrier = threading.Barrier(8)

    def worker(n: int) -> None:
        barrier.wait()
        try:
            with sim.db.transaction() as conn:
                results.append(payments_service.execute(conn, workspace_id, proposal["id"], f"concurrent-{n:04d}",
                                                        sim.clock.now(), sim.clock.today("Asia/Dhaka")))
        except Exception as exc:  # noqa: BLE001 - record any unexpected failure
            results.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(isinstance(r, dict) for r in results), results
    assert len({r["execution_id"] for r in results}) == 1  # type: ignore[index]
    assert sum(1 for r in results if not r["replayed"]) == 1  # type: ignore[index]
    assert balance_of(c) == "29000.00"
    assert len(payment_transactions(c)) == 2


def test_failure_mid_execution_rolls_back_everything(sim, monkeypatch) -> None:
    c = sim.client()
    receive_family(c)
    proposal = ok(approve(c, propose(c, "A")))
    real_post = payments_service.ledger.post
    calls = {"n": 0}

    def failing_post(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:  # the fee debit, after the principal debit was written
            raise RuntimeError("injected failure")
        return real_post(*args, **kwargs)

    monkeypatch.setattr(payments_service.ledger, "post", failing_post)
    with pytest.raises(RuntimeError):
        with sim.db.transaction() as conn:
            payments_service.execute(conn, ok(c.get("/api/session"))["workspace_id"], proposal["id"], "rollback-key-1",
                                     sim.clock.now(), sim.clock.today("Asia/Dhaka"))
    monkeypatch.setattr(payments_service.ledger, "post", real_post)
    assert balance_of(c) == "110000.00"
    assert payment_transactions(c) == []
    assert tuition(c)["status"] == "open"
    assert ok(c.get(f"/api/payments/proposals/{proposal['id']}"))["status"] == "approved"
    assert ok(c.get("/api/payments/executions/status", params={"idempotency_key": "rollback-key-1"}))["found"] is False
    # After the fault is gone, the same key executes normally exactly once.
    assert ok(execute(c, proposal, "rollback-key-1"))["balance_after"] == "29000.00"


def test_insufficient_funds_at_execution_rolls_back(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = ok(approve(c, propose(c, "A")))
    # Money leaves the account after approval.
    ok(post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "expense", "category": "other",
                                     "amount": "50000.00", "occurred_on": "2026-10-19"}))
    response = execute(c, proposal)
    assert response.status_code == 409 and response.json()["error"]["code"] == "insufficient_funds"
    assert balance_of(c) == "60000.00"
    assert payment_transactions(c) == [] and tuition(c)["status"] == "open"
    assert ok(c.get(f"/api/payments/proposals/{proposal['id']}"))["status"] == "failed"


def test_reserve_rechecked_at_execution(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = ok(approve(c, propose(c, "A")))
    ok(post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "expense", "category": "other",
                                     "amount": "10000.00", "occurred_on": "2026-10-19"}))
    response = execute(c, proposal)
    assert response.json()["error"]["code"] == "reserve_breach"
    assert balance_of(c) == "100000.00" and payment_transactions(c) == []


def test_expired_proposal_rejected(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = propose(c, "A")
    sim.clock.advance(minutes=16)
    response = approve(c, proposal)
    assert response.status_code == 409 and response.json()["error"]["code"] == "proposal_expired"
    assert ok(c.get(f"/api/payments/proposals/{proposal['id']}"))["status"] == "expired"
    # Approved, then expired before execution.
    fresh = ok(approve(c, propose(c, "A")))
    sim.clock.advance(minutes=15)
    response = execute(c, fresh)
    assert response.status_code == 409 and response.json()["error"]["code"] == "proposal_expired"
    assert balance_of(c) == "110000.00" and payment_transactions(c) == []
    # Refresh creates a new version that must be reviewed and approved again.
    refreshed = ok(post(c, f"/api/payments/proposals/{fresh['id']}/refresh"))
    assert (refreshed["status"], refreshed["version"]) == ("ready_for_review", 2)
    assert execute(c, refreshed).json()["error"]["code"] == "not_approved"


def test_approval_must_name_the_reviewed_version(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = propose(c, "A")
    wrong_hash = post(c, f"/api/payments/proposals/{proposal['id']}/approve", {"version": 1, "terms_hash": "0" * 64})
    assert wrong_hash.json()["error"]["code"] == "terms_changed"
    refreshed = ok(post(c, f"/api/payments/proposals/{proposal['id']}/refresh"))
    stale = approve(c, proposal)  # version 1 and its hash, after version 2 exists
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "terms_changed"
    assert ok(approve(c, refreshed))["approved_version"] == 2


def test_modified_bill_invalidates_approval(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = ok(approve(c, propose(c, "A")))
    bill = tuition(c)
    ok(c.put(f"/api/bills/{bill['id']}", json={"description": bill["description"], "payee": bill["payee"], "category": "tuition",
                                               "amount": "1100.00", "currency": "AUD", "due_date": bill["due_date"]}, headers=ORIGIN))
    assert ok(c.get(f"/api/payments/proposals/{proposal['id']}"))["status"] == "cancelled"
    response = execute(c, proposal)
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_approved"
    assert balance_of(c) == "110000.00" and payment_transactions(c) == []
    # A new proposal uses the new terms: AUD 1100 / 0.0125 = BDT 88000 + 1000 fee.
    assert propose(c, "A")["terms"]["total_debit"] == "89000.00"


def test_cancellation(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = ok(approve(c, propose(c, "A")))
    assert ok(post(c, f"/api/payments/proposals/{proposal['id']}/cancel"))["status"] == "cancelled"
    assert approve(c, proposal).json()["error"]["code"] == "invalid_state"
    assert execute(c, proposal).json()["error"]["code"] == "not_approved"
    assert post(c, f"/api/payments/proposals/{proposal['id']}/cancel").status_code == 409
    assert balance_of(c) == "110000.00"


def test_viewing_or_preparing_never_approves(sim) -> None:
    c = sim.client()
    receive_family(c)
    proposal = propose(c, "B")
    for _ in range(3):
        assert ok(c.get(f"/api/payments/proposals/{proposal['id']}"))["status"] == "ready_for_review"
    assert ok(c.get("/api/payments/proposals"))["proposals"][0]["status"] == "ready_for_review"
    assert execute(c, proposal).json()["error"]["code"] == "not_approved"


def test_client_cannot_supply_amounts(sim) -> None:
    c = sim.client()
    response = post(c, "/api/payments/proposals", {"bill_id": tuition(c)["id"], "source_account_id": bdt_account(c),
                                                   "route": "A", "total_debit": "1.00"})
    assert response.status_code == 422  # unknown fields are rejected; terms are server-computed


def test_foreign_workspace_cannot_touch_payments(sim) -> None:
    alice, bob = sim.client(), sim.client()
    receive_family(alice)
    proposal = ok(approve(alice, propose(alice, "A")))
    alice_bill = tuition(alice)
    assert bob.get(f"/api/payments/proposals/{proposal['id']}").status_code == 404
    assert approve(bob, proposal).status_code == 404
    assert execute(bob, proposal, "bob-key-00001").status_code == 404
    assert post(bob, f"/api/payments/proposals/{proposal['id']}/cancel").status_code == 404
    assert bob.get(f"/api/bills/{alice_bill['id']}/routes", params={"source_account_id": bdt_account(bob)}).status_code == 404
    assert post(bob, "/api/payments/proposals", {"bill_id": alice_bill["id"], "source_account_id": bdt_account(bob),
                                                 "route": "A"}).status_code == 404
    assert post(bob, "/api/payments/proposals", {"bill_id": tuition(bob)["id"], "source_account_id": bdt_account(alice),
                                                 "route": "A"}).status_code == 404
    result = ok(execute(alice, proposal, "alice-key-0001"))
    assert bob.get(f"/api/payments/executions/{result['execution_id']}").status_code == 404
    assert ok(bob.get("/api/payments/executions/status", params={"idempotency_key": "alice-key-0001"}))["found"] is False
    assert balance_of(bob) == "100000.00" and balance_of(alice) == "29000.00"


def test_idempotency_key_cannot_be_reused_for_another_payment(sim) -> None:
    c = sim.client()
    receive_family(c)
    first = ok(approve(c, propose(c, "A")))
    ok(execute(c, first, "shared-key-001"))
    ok(post(c, "/api/bills", {"description": "Campus fee (demo)", "payee": "Example University (fictional)", "category": "campus",
                              "amount": "100.00", "currency": "AUD", "due_date": "2026-11-30"}))
    campus = next(b for b in ok(c.get("/api/bills"))["bills"] if b["status"] == "open")
    second = ok(post(c, "/api/payments/proposals", {"bill_id": campus["id"], "source_account_id": bdt_account(c), "route": "C"}))
    second = ok(approve(c, second))
    response = execute(c, second, "shared-key-001")
    assert response.status_code == 409 and response.json()["error"]["code"] == "idempotency_key_reused"


def test_refund_record_does_not_move_money(sim) -> None:
    c = sim.client()
    receive_family(c)
    result = ok(execute(c, ok(approve(c, propose(c, "A")))))
    too_much = post(c, f"/api/payments/executions/{result['execution_id']}/refunds", {"amount": "1000.01", "reason": "x"})
    assert too_much.status_code == 422
    receipt = ok(post(c, f"/api/payments/executions/{result['execution_id']}/refunds", {"amount": "200.00", "reason": "Course dropped"}))
    assert receipt["refunds"][0]["amount"] == "200.00" and receipt["refunds"][0]["currency"] == "AUD"
    assert balance_of(c) == "29000.00"


def test_routes_only_from_bdt_accounts(sim) -> None:
    c = sim.client()
    aud = next(a["id"] for a in ok(c.get("/api/accounts"))["accounts"] if a["currency"] == "AUD")
    response = c.get(f"/api/bills/{tuition(c)['id']}/routes", params={"source_account_id": aud})
    assert response.status_code == 422 and response.json()["error"]["code"] == "no_route"


def test_audit_events_recorded(sim) -> None:
    c = sim.client()
    receive_family(c)
    ok(execute(c, ok(approve(c, propose(c, "A")))))
    types = [e["event_type"] for e in ok(c.get("/api/activity"))["events"]]
    for expected in ("payment_proposed", "payment_approved", "payment_executed_simulated", "contribution_received"):
        assert expected in types
