"""Stage D release checks for risks not covered elsewhere: persistence of financial and
assistant records across a backend restart, and historical rate-snapshot consistency."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.clock import SimulationClock
from app.deps import SESSION_COOKIE
from app.main import create_app

from .conftest import FIXTURE_START, ORIGIN, balance_of, bdt_account, ok


def post(client, path, body=None):  # type: ignore[no-untyped-def]
    return client.post(path, json=body or {}, headers=ORIGIN)


def _pay_fixture(c) -> dict:  # type: ignore[no-untyped-def,type-arg]
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    ok(post(c, f"/api/contributions/{contribution['id']}/receive"))
    bill = ok(c.get("/api/bills"))["bills"][0]
    p = ok(post(c, "/api/payments/proposals", {"bill_id": bill["id"], "route": "A", "source_account_id": bdt_account(c)}))
    ok(post(c, f"/api/payments/proposals/{p['id']}/approve", {"version": p["version"], "terms_hash": p["terms_hash"]}))
    return ok(post(c, f"/api/payments/proposals/{p['id']}/execute", {"idempotency_key": "release-0001"}))


def _app(settings):  # type: ignore[no-untyped-def]
    app = create_app(settings)
    app.state.clock = SimulationClock(FIXTURE_START)
    return app


def test_financial_and_assistant_records_survive_backend_restart(settings) -> None:
    app = _app(settings)
    with TestClient(app, base_url="http://localhost:8000") as c:
        ok(post(c, "/api/session"))
        execution = _pay_fixture(c)
        ok(post(c, "/api/funding/applications", {"name": "Bursary (demo)", "deadline": "2026-10-30"}))
        with app.state.db.transaction() as conn:  # a stored assistant conversation (no model needed)
            ws = ok(c.get("/api/session"))["workspace_id"]
            conn.execute("INSERT INTO conversations (id, workspace_id, title, created_at, updated_at) VALUES"
                         " ('conv_restart', ?, 'Restart check', '2026-10-19T03:00:00Z', '2026-10-19T03:00:00Z')", (ws,))
        token = c.cookies[SESSION_COOKIE]
        before = ok(c.get("/api/reports?month=2026-10"))

    with TestClient(_app(settings), base_url="http://localhost:8000") as restarted:
        restarted.cookies.set(SESSION_COOKIE, token)
        assert balance_of(restarted) == "29000.00"
        executions = ok(restarted.get("/api/payments/executions"))["executions"]
        assert [e["execution_id"] for e in executions] == [execution["execution_id"]]
        assert ok(restarted.get("/api/bills"))["bills"][0]["status"] == "settled"
        assert ok(restarted.get("/api/reports?month=2026-10"))["totals"] == before["totals"]
        assert [a["name"] for a in ok(restarted.get("/api/funding"))["applications"]] == ["Bursary (demo)"]
        assert [c["id"] for c in ok(restarted.get("/api/assistant/conversations"))["conversations"]] == ["conv_restart"]
        # A retried execution after the restart replays, it does not debit again.
        retry = ok(post(restarted, f"/api/payments/proposals/{execution['proposal_id']}/execute", {"idempotency_key": "release-0002"}))
        assert retry["replayed"] is True and balance_of(restarted) == "29000.00"


def test_rate_change_after_execution_keeps_historical_amounts(sim) -> None:
    c = sim.client()
    execution = _pay_fixture(c)
    receipt_before = ok(c.get(f"/api/payments/executions/{execution['execution_id']}"))
    sim.clock.advance(minutes=1)
    ok(post(c, "/api/rates/manual", {"base": "BDT", "quote": "AUD", "rate": "0.0100"}))
    receipt_after = ok(c.get(f"/api/payments/executions/{execution['execution_id']}"))
    assert receipt_after == receipt_before  # receipt keeps the snapshot it used
    assert balance_of(c) == "29000.00"
    debits = [t for t in ok(c.get("/api/transactions"))["transactions"] if t["kind"] in ("payment", "fee")]
    assert sorted(t["amount"] for t in debits) == ["1000.00", "80000.00"]
    # Views use the latest snapshot (documented valuation policy): BDT 80,000 now values at AUD 800.00.
    r = ok(c.get("/api/rates/convert", params={"amount": "80000", "from": "BDT", "to": "AUD"}))
    assert (r["result"], r["rate"]["mode"]) == ("800.00", "manual")


def test_rate_change_after_review_requires_a_fresh_review(sim) -> None:
    c = sim.client()
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    ok(post(c, f"/api/contributions/{contribution['id']}/receive"))
    bill = ok(c.get("/api/bills"))["bills"][0]
    p = ok(post(c, "/api/payments/proposals", {"bill_id": bill["id"], "route": "A", "source_account_id": bdt_account(c)}))
    sim.clock.advance(minutes=1)
    ok(post(c, "/api/rates/manual", {"base": "BDT", "quote": "AUD", "rate": "0.0124"}))
    reviewed = ok(c.get(f"/api/payments/proposals/{p['id']}"))
    assert reviewed["terms"]["total_debit"] == p["terms"]["total_debit"]  # the reviewed terms do not drift
    assert reviewed["terms"]["rate"] == p["terms"]["rate"]
    # Refreshing creates a new version with the new rate and clears nothing silently.
    refreshed = ok(post(c, f"/api/payments/proposals/{p['id']}/refresh"))
    assert refreshed["version"] == p["version"] + 1 and refreshed["terms"]["rate"]["rate"] == "0.0124"
    stale = post(c, f"/api/payments/proposals/{p['id']}/approve", {"version": p["version"], "terms_hash": p["terms_hash"]})
    assert stale.status_code == 409
    assert balance_of(c) == "110000.00"
