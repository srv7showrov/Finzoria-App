"""Reviewed, explicitly approved, SIMULATED tuition payments.

Rules (demo "Reserve and payment semantics"):
- The server computes every amount. Clients and the model send only IDs and choices.
- A proposal's material terms are hashed; approval names the exact version and hash
  reviewed. Refreshing terms creates a new version and clears approval.
- Approval and execution both re-check ownership, expiry, bill version, available
  funds and the strict reserve floor. Expected contributions never count as cash.
- Execution runs inside one immediate SQLite transaction: payment debit, fee debit,
  bill settlement, proposal status, execution record and audit event commit together
  or not at all. A unique idempotency key and one-execution-per-proposal constraint
  mean retries and concurrent clicks return the first result and never debit twice.
- No real money moves; nothing is sent to any provider.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal

from ..errors import DomainError, not_found
from ..money import parse_amount, to_string
from . import ledger
from . import rates as rates_service
from .bills import get_bill
from .common import iso, log_event, new_id, parse_iso
from .funding import get_reserve
from .transfer_routes import QUOTE_TTL_MINUTES, ROUTES, cost, get_route, require_route_currency

OPEN_STATES = ("draft", "ready_for_review", "approved")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,100}$")


def terms_hash(terms: dict[str, object]) -> str:
    canonical = json.dumps(terms, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- route comparison --------------------------------------------------------------


def _reserve_for(conn: sqlite3.Connection, workspace_id: str, account_id: str) -> Decimal:
    reserve = get_reserve(conn, workspace_id)
    if reserve and reserve["account_id"] == account_id and reserve["strict"]:
        return Decimal(str(reserve["floor_amount"]))
    return Decimal(0)


def compare_routes(conn: sqlite3.Connection, workspace_id: str, bill_id: str, source_account_id: str, today: date) -> dict[str, object]:
    bill = get_bill(conn, workspace_id, bill_id)
    if bill["status"] != "open":
        raise DomainError(409, "invalid_state", "This bill is not open.")
    account = ledger.get_account_row(conn, workspace_id, source_account_id)
    require_route_currency(account["currency"])
    rate = rates_service.get_rate(conn, workspace_id, account["currency"], str(bill["currency"]))
    current = ledger.balance(conn, workspace_id, source_account_id)
    floor = _reserve_for(conn, workspace_id, source_account_id)
    due = date.fromisoformat(str(bill["due_date"]))
    cur = account["currency"]
    routes = []
    for code, route in ROUTES.items():
        c = cost(route, Decimal(str(bill["amount"])), rate.rate, cur, today)
        after = current - c.total
        routes.append({
            "route": code, "fictional": True, "assumption": route.assumption, "delivery_days": route.delivery_days,
            "principal": to_string(c.principal, cur), "fee": to_string(c.fee, cur), "total_debit": to_string(c.total, cur),
            "initiation_date": c.initiation.isoformat(), "estimated_arrival": c.arrival.isoformat(),
            "on_time": c.arrival <= due, "funds_ok": current >= c.total, "reserve_ok": after >= floor,
            "balance_after": to_string(after, cur), "gap_to_floor": to_string(after - floor, cur),
        })
    return {
        "objective": {"recipient_amount": bill["amount"], "recipient_currency": bill["currency"], "due_date": bill["due_date"],
                      "reserve_floor": to_string(floor, cur), "source_currency": cur},
        "source_account": {"id": account["id"], "name": account["name"], "currency": cur, "balance": to_string(current, cur)},
        "rate": rate.as_dict(),
        "quote_valid_minutes": QUOTE_TTL_MINUTES,
        "limits": ["fictional_routes", "calendar_days", "not_provider_quotes", "expected_funds_not_counted"],
        "routes": routes,
    }


# --- proposals ------------------------------------------------------------------


def _build_terms(conn: sqlite3.Connection, workspace_id: str, bill: dict[str, object], account: sqlite3.Row,
                 route_code: str, now: datetime, today: date) -> tuple[dict[str, object], str]:
    route = get_route(route_code)
    cur = account["currency"]
    require_route_currency(cur)
    rate = rates_service.get_rate(conn, workspace_id, cur, str(bill["currency"]))
    if rate.snapshot_id is None:  # pragma: no cover - identity rates never reach routes
        raise DomainError(422, "unsupported_pair", "A rate snapshot is required.")
    c = cost(route, Decimal(str(bill["amount"])), rate.rate, cur, today)
    expires = now + timedelta(minutes=QUOTE_TTL_MINUTES)
    quote_id = new_id("quote")
    conn.execute(
        "INSERT INTO quotes (id, workspace_id, route, source_currency, target_currency, rate, rate_snapshot_id, fee,"
        " delivery_days, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (quote_id, workspace_id, route.code, cur, bill["currency"], format(rate.rate, "f"), rate.snapshot_id,
         to_string(c.fee, cur), route.delivery_days, iso(now), iso(expires)),
    )
    terms: dict[str, object] = {
        "simulated": True,
        "bill": {k: bill[k] for k in ("id", "version", "description", "payee", "category", "amount", "currency", "due_date")},
        "source_account": {"id": account["id"], "name": account["name"], "currency": cur},
        "route": {"code": route.code, "delivery_days": route.delivery_days, "assumption": route.assumption, "fictional": True},
        "quote": {"id": quote_id, "created_at": iso(now), "expires_at": iso(expires)},
        "rate": rate.as_dict(),
        "recipient": str(bill["payee"]),
        "recipient_amount": bill["amount"],
        "recipient_currency": bill["currency"],
        "source_currency": cur,
        "principal": to_string(c.principal, cur),
        "fee": to_string(c.fee, cur),
        "total_debit": to_string(c.total, cur),
        "initiation_date": c.initiation.isoformat(),
        "estimated_arrival": c.arrival.isoformat(),
        "on_time": c.arrival <= date.fromisoformat(str(bill["due_date"])),
    }
    return terms, terms_hash(terms)


def create_proposal(conn: sqlite3.Connection, workspace_id: str, bill_id: str, source_account_id: str, route_code: str,
                    now: datetime, today: date) -> dict[str, object]:
    bill = get_bill(conn, workspace_id, bill_id)
    if bill["status"] != "open":
        raise DomainError(409, "invalid_state", "This bill is not open.")
    account = ledger.get_account_row(conn, workspace_id, source_account_id)
    terms, digest = _build_terms(conn, workspace_id, bill, account, route_code, now, today)
    proposal_id = new_id("prop")
    conn.execute(
        "INSERT INTO payment_proposals (id, workspace_id, bill_id, source_account_id, quote_id, status, version, terms,"
        " terms_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'ready_for_review', 1, ?, ?, ?, ?)",
        (proposal_id, workspace_id, bill_id, source_account_id, terms["quote"]["id"],  # type: ignore[index]
         json.dumps(terms, sort_keys=True), digest, iso(now), iso(now)),
    )
    log_event(conn, workspace_id, now, "payment_proposed", "proposal", proposal_id, route=route_code,
              total_debit=terms["total_debit"], currency=terms["source_currency"], simulated=True)
    return get_proposal(conn, workspace_id, proposal_id, now)


def _row(conn: sqlite3.Connection, workspace_id: str, proposal_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM payment_proposals WHERE workspace_id = ? AND id = ?", (workspace_id, proposal_id)).fetchone()
    if row is None:
        raise not_found("Payment proposal")
    return row


def _expired(terms: dict[str, object], now: datetime) -> bool:
    return now >= parse_iso(str(terms["quote"]["expires_at"]))  # type: ignore[index]


def _checks(conn: sqlite3.Connection, workspace_id: str, row: sqlite3.Row, terms: dict[str, object], now: datetime) -> dict[str, object]:
    cur = str(terms["source_currency"])
    total = Decimal(str(terms["total_debit"]))
    current = ledger.balance(conn, workspace_id, row["source_account_id"])
    floor = _reserve_for(conn, workspace_id, row["source_account_id"])
    bill = get_bill(conn, workspace_id, row["bill_id"])
    bill_settled = bill["status"] == "settled"
    bill_current = bill["status"] == "open" and bill["version"] == terms["bill"]["version"]  # type: ignore[index]
    after = current - total
    blocking = []
    # A bill already paid by another proposal is the decisive reason, whatever the balance.
    if bill_settled:
        blocking.append("bill_settled")
    if _expired(terms, now):
        blocking.append("expired")
    if not bill_current and not bill_settled:
        blocking.append("bill_changed")
    if current < total:
        blocking.append("insufficient_funds")
    if after < floor:
        blocking.append("reserve_breach")
    if terms_hash(terms) != row["terms_hash"]:  # pragma: no cover - stored terms are never edited
        blocking.append("terms_changed")
    return {
        "checked_at": iso(now),
        "balance_now": to_string(current, cur),
        "balance_after": to_string(after, cur),
        "reserve_floor": to_string(floor, cur),
        "gap_to_floor": to_string(after - floor, cur),
        "funds_ok": current >= total,
        "reserve_ok": after >= floor,
        "bill_current": bill_current,
        "bill_settled": bill_settled,
        "expired": _expired(terms, now),
        "blocking": blocking,
        "currency": cur,
    }


def _expire_if_needed(conn: sqlite3.Connection, workspace_id: str, row: sqlite3.Row, terms: dict[str, object], now: datetime) -> bool:
    if row["status"] in OPEN_STATES and _expired(terms, now):
        conn.execute(
            "UPDATE payment_proposals SET status = 'expired', status_reason = 'quote_expired', updated_at = ?"
            " WHERE workspace_id = ? AND id = ? AND status IN ('draft', 'ready_for_review', 'approved')",
            (iso(now), workspace_id, row["id"]),
        )
        log_event(conn, workspace_id, now, "payment_expired", "proposal", row["id"])
        return True
    return False


def get_proposal(conn: sqlite3.Connection, workspace_id: str, proposal_id: str, now: datetime, *, persist_expiry: bool = False) -> dict[str, object]:
    row = _row(conn, workspace_id, proposal_id)
    terms = json.loads(row["terms"])
    if persist_expiry and _expire_if_needed(conn, workspace_id, row, terms, now):
        row = _row(conn, workspace_id, proposal_id)
    status = row["status"]
    status_reason = row["status_reason"]
    # An outstanding proposal whose bill was settled by another payment is no longer available
    # (also covers proposals left open before sibling proposals were closed at execution time).
    if status in OPEN_STATES and get_bill(conn, workspace_id, row["bill_id"])["status"] == "settled":
        status, status_reason = "cancelled", "bill_settled"
    elif status in OPEN_STATES and _expired(terms, now):
        status, status_reason = "expired", "quote_expired"
    execution = conn.execute(
        "SELECT id, result FROM executions WHERE workspace_id = ? AND proposal_id = ?", (workspace_id, proposal_id)
    ).fetchone()
    return {
        "id": row["id"],
        "status": status,
        "status_reason": status_reason,
        "version": row["version"],
        "terms": terms,
        "terms_hash": row["terms_hash"],
        "approved_version": row["approved_version"],
        "approved_at": row["approved_at"],
        "created_at": row["created_at"],
        "simulated": True,
        "checks": _checks(conn, workspace_id, row, terms, now) if status in OPEN_STATES else None,
        "execution": json.loads(execution["result"]) if execution else None,
    }


def list_proposals(conn: sqlite3.Connection, workspace_id: str, now: datetime) -> list[dict[str, object]]:
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM payment_proposals WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC", (workspace_id,)
    )]
    return [get_proposal(conn, workspace_id, i, now) for i in ids]


def _blocked(code: str) -> DomainError:
    messages = {
        "expired": ("proposal_expired", "This quote has expired. Refresh the terms and review again."),
        "bill_settled": ("bill_settled", "This bill is already settled by another payment. This proposal can no longer be approved or run."),
        "bill_changed": ("terms_changed", "The bill changed after these terms were prepared. Review fresh terms."),
        "insufficient_funds": ("insufficient_funds", "The source account does not have enough available funds."),
        "reserve_breach": ("reserve_breach", "This payment would take the account below its reserve floor."),
        "terms_changed": ("terms_changed", "The terms changed. Review the latest version."),
    }
    error_code, message = messages[code]
    return DomainError(409, error_code, message)


def approve(conn: sqlite3.Connection, workspace_id: str, proposal_id: str, version: int, digest: str, now: datetime) -> dict[str, object]:
    """Explicit approval by the session for the exact version and hash it reviewed."""
    row = _row(conn, workspace_id, proposal_id)
    terms = json.loads(row["terms"])
    if row["status"] == "approved" and row["approved_version"] == version and row["approved_hash"] == digest and not _expired(terms, now):
        return get_proposal(conn, workspace_id, proposal_id, now)
    if _expire_if_needed(conn, workspace_id, row, terms, now):
        return {"error": _blocked("expired")}
    if row["status_reason"] == "bill_settled" or get_bill(conn, workspace_id, row["bill_id"])["status"] == "settled":
        raise _blocked("bill_settled")
    if row["status"] != "ready_for_review":
        raise DomainError(409, "invalid_state", f"A proposal in state {row['status']} cannot be approved.")
    if version != row["version"] or digest != row["terms_hash"]:
        raise DomainError(409, "terms_changed", "These are not the latest terms. Review the current version before approving.")
    checks = _checks(conn, workspace_id, row, terms, now)
    if checks["blocking"]:
        raise _blocked(str(checks["blocking"][0]))  # type: ignore[index]
    conn.execute(
        "UPDATE payment_proposals SET status = 'approved', approved_version = ?, approved_hash = ?, approved_at = ?,"
        " updated_at = ? WHERE workspace_id = ? AND id = ? AND status = 'ready_for_review' AND version = ?",
        (version, digest, iso(now), iso(now), workspace_id, proposal_id, version),
    )
    log_event(conn, workspace_id, now, "payment_approved", "proposal", proposal_id, version=version, approved_by="session")
    return get_proposal(conn, workspace_id, proposal_id, now)


def cancel(conn: sqlite3.Connection, workspace_id: str, proposal_id: str, now: datetime) -> dict[str, object]:
    row = _row(conn, workspace_id, proposal_id)
    if row["status"] not in OPEN_STATES:
        raise DomainError(409, "invalid_state", f"A proposal in state {row['status']} cannot be cancelled.")
    conn.execute(
        "UPDATE payment_proposals SET status = 'cancelled', status_reason = 'user_cancelled', updated_at = ?"
        " WHERE workspace_id = ? AND id = ?",
        (iso(now), workspace_id, proposal_id),
    )
    log_event(conn, workspace_id, now, "payment_cancelled", "proposal", proposal_id)
    return get_proposal(conn, workspace_id, proposal_id, now)


def refresh(conn: sqlite3.Connection, workspace_id: str, proposal_id: str, now: datetime, today: date) -> dict[str, object]:
    """Re-quote with current data as a new version. Any approval is cleared."""
    row = _row(conn, workspace_id, proposal_id)
    bill = get_bill(conn, workspace_id, row["bill_id"])
    if row["status_reason"] == "bill_settled" or (bill["status"] == "settled" and row["status"] != "executed_simulated"):
        raise _blocked("bill_settled")
    if row["status"] not in (*OPEN_STATES, "expired"):
        raise DomainError(409, "invalid_state", f"A proposal in state {row['status']} cannot be refreshed.")
    if bill["status"] != "open":
        raise DomainError(409, "invalid_state", "This bill is not open.")
    old_terms = json.loads(row["terms"])
    account = ledger.get_account_row(conn, workspace_id, row["source_account_id"])
    terms, digest = _build_terms(conn, workspace_id, bill, account, str(old_terms["route"]["code"]), now, today)
    conn.execute(
        "UPDATE payment_proposals SET status = 'ready_for_review', version = version + 1, terms = ?, terms_hash = ?,"
        " quote_id = ?, approved_version = NULL, approved_hash = NULL, approved_at = NULL, status_reason = NULL,"
        " updated_at = ? WHERE workspace_id = ? AND id = ?",
        (json.dumps(terms, sort_keys=True), digest, terms["quote"]["id"], iso(now), workspace_id, proposal_id),  # type: ignore[index]
    )
    log_event(conn, workspace_id, now, "payment_refreshed", "proposal", proposal_id, version=row["version"] + 1)
    return get_proposal(conn, workspace_id, proposal_id, now)


def _fail(conn: sqlite3.Connection, workspace_id: str, proposal_id: str, reason: str, now: datetime) -> None:
    status = "expired" if reason == "expired" else "cancelled" if reason == "bill_settled" else "failed"
    conn.execute(
        "UPDATE payment_proposals SET status = ?, status_reason = ?, updated_at = ? WHERE workspace_id = ? AND id = ?",
        (status, reason, iso(now), workspace_id, proposal_id),
    )
    log_event(conn, workspace_id, now, "payment_failed" if status == "failed" else "payment_expired", "proposal",
              proposal_id, reason=reason)


def execute(conn: sqlite3.Connection, workspace_id: str, proposal_id: str, idempotency_key: str,
            now: datetime, today: date) -> dict[str, object]:
    """Run inside Database.transaction(). Returns the execution result, or {"error": DomainError}
    when the proposal was moved to failed/expired (that status change must still commit)."""
    if not IDEMPOTENCY_KEY.fullmatch(idempotency_key or ""):
        raise DomainError(422, "invalid_idempotency_key", "Send an idempotency key of 8-100 letters, digits, '-' or '_'.")
    prior = conn.execute(
        "SELECT proposal_id, result FROM executions WHERE workspace_id = ? AND idempotency_key = ?",
        (workspace_id, idempotency_key),
    ).fetchone()
    if prior is not None:
        if prior["proposal_id"] != proposal_id:
            raise DomainError(409, "idempotency_key_reused", "This idempotency key belongs to another payment.")
        return {**json.loads(prior["result"]), "replayed": True}

    row = _row(conn, workspace_id, proposal_id)
    if row["status"] == "executed_simulated":
        existing = conn.execute(
            "SELECT result FROM executions WHERE workspace_id = ? AND proposal_id = ?", (workspace_id, proposal_id)
        ).fetchone()
        return {**json.loads(existing["result"]), "replayed": True}
    if row["status_reason"] == "bill_settled":
        raise _blocked("bill_settled")
    if row["status"] != "approved":
        raise DomainError(409, "not_approved", "This payment has not been approved in its current version.")
    terms = json.loads(row["terms"])
    if row["approved_version"] != row["version"] or row["approved_hash"] != row["terms_hash"] or terms_hash(terms) != row["terms_hash"]:
        _fail(conn, workspace_id, proposal_id, "terms_changed", now)
        return {"error": _blocked("terms_changed")}
    checks = _checks(conn, workspace_id, row, terms, now)
    if checks["blocking"]:
        reason = str(checks["blocking"][0])  # type: ignore[index]
        _fail(conn, workspace_id, proposal_id, reason, now)
        return {"error": _blocked(reason)}

    cur = str(terms["source_currency"])
    principal, fee, total = (Decimal(str(terms[k])) for k in ("principal", "fee", "total_debit"))
    before = ledger.balance(conn, workspace_id, row["source_account_id"])
    execution_id = new_id("exe")
    bill = terms["bill"]
    payment_txn = ledger.post(conn, workspace_id, row["source_account_id"], "payment", principal, str(bill["category"]),
                              f"{bill['description']} — {bill['payee']} (simulated)", today, now,
                              source_type="execution", source_id=execution_id)
    fee_txn = ledger.post(conn, workspace_id, row["source_account_id"], "fee", fee, "transfer_fee",
                          f"Route {terms['route']['code']} fee (simulated)", today, now,
                          source_type="execution", source_id=execution_id)
    settled = conn.execute(
        "UPDATE bills SET status = 'settled', settled_on = ?, settled_by_execution_id = ?, updated_at = ?"
        " WHERE workspace_id = ? AND id = ? AND status = 'open' AND version = ?",
        (today.isoformat(), execution_id, iso(now), workspace_id, bill["id"], bill["version"]),
    ).rowcount
    if settled != 1:  # pragma: no cover - guarded by checks inside the same transaction
        raise DomainError(409, "terms_changed", "The bill changed during execution.")
    after = ledger.balance(conn, workspace_id, row["source_account_id"])
    result = {
        "execution_id": execution_id,
        "receipt_number": f"SIM-{execution_id[-8:].upper()}",
        "proposal_id": proposal_id,
        "proposal_version": row["version"],
        "idempotency_key": idempotency_key,
        "status": "executed_simulated",
        "simulated": True,
        "executed_at": iso(now),
        "executed_on": today.isoformat(),
        "bill_id": bill["id"],
        "bill_description": bill["description"],
        "recipient": terms["recipient"],
        "recipient_amount": terms["recipient_amount"],
        "recipient_currency": terms["recipient_currency"],
        "route": terms["route"]["code"],
        "rate": terms["rate"],
        "source_account_id": row["source_account_id"],
        "source_account_name": terms["source_account"]["name"],
        "source_currency": cur,
        "principal": to_string(principal, cur),
        "fee": to_string(fee, cur),
        "total_debit": to_string(total, cur),
        "balance_before": to_string(before, cur),
        "balance_after": to_string(after, cur),
        "estimated_arrival": terms["estimated_arrival"],
        "transaction_ids": [payment_txn, fee_txn],
        "replayed": False,
    }
    conn.execute(
        "INSERT INTO executions (id, workspace_id, proposal_id, idempotency_key, status, result, created_at)"
        " VALUES (?, ?, ?, ?, 'executed_simulated', ?, ?)",
        (execution_id, workspace_id, proposal_id, idempotency_key, json.dumps(result, sort_keys=True), iso(now)),
    )
    conn.execute(
        "UPDATE payment_proposals SET status = 'executed_simulated', status_reason = NULL, updated_at = ?"
        " WHERE workspace_id = ? AND id = ? AND status = 'approved'",
        (iso(now), workspace_id, proposal_id),
    )
    # Other open proposals for this bill can no longer be paid; close them (their terms stay as history).
    siblings = [r["id"] for r in conn.execute(
        "SELECT id FROM payment_proposals WHERE workspace_id = ? AND bill_id = ? AND id != ?"
        " AND status IN ('draft', 'ready_for_review', 'approved')",
        (workspace_id, bill["id"], proposal_id),
    )]
    for sibling in siblings:
        conn.execute(
            "UPDATE payment_proposals SET status = 'cancelled', status_reason = 'bill_settled', updated_at = ?"
            " WHERE workspace_id = ? AND id = ?",
            (iso(now), workspace_id, sibling),
        )
        log_event(conn, workspace_id, now, "payment_cancelled", "proposal", sibling, reason="bill_settled")
    log_event(conn, workspace_id, now, "payment_executed_simulated", "execution", execution_id, proposal_id=proposal_id,
              total_debit=result["total_debit"], currency=cur, balance_after=result["balance_after"], simulated=True)
    return result


def execution_status(conn: sqlite3.Connection, workspace_id: str, idempotency_key: str) -> dict[str, object]:
    """Safe lookup after a lost response: query this before retrying."""
    row = conn.execute(
        "SELECT result FROM executions WHERE workspace_id = ? AND idempotency_key = ?", (workspace_id, idempotency_key)
    ).fetchone()
    if row is None:
        return {"found": False, "idempotency_key": idempotency_key}
    return {"found": True, "result": json.loads(row["result"])}


def list_executions(conn: sqlite3.Connection, workspace_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT result FROM executions WHERE workspace_id = ? ORDER BY created_at DESC, rowid DESC", (workspace_id,)
    ).fetchall()
    return [json.loads(r["result"]) for r in rows]


def get_execution(conn: sqlite3.Connection, workspace_id: str, execution_id: str) -> dict[str, object]:
    row = conn.execute(
        "SELECT result FROM executions WHERE workspace_id = ? AND id = ?", (workspace_id, execution_id)
    ).fetchone()
    if row is None:
        raise not_found("Execution")
    result = json.loads(row["result"])
    refunds = conn.execute(
        "SELECT id, amount, currency, reason, created_at FROM refunds WHERE workspace_id = ? AND execution_id = ?"
        " ORDER BY created_at", (workspace_id, execution_id),
    ).fetchall()
    return {**result, "refunds": [dict(r) for r in refunds]}


def record_refund(conn: sqlite3.Connection, workspace_id: str, execution_id: str, amount: str, reason: str,
                  now: datetime) -> dict[str, object]:
    """Manual record of an expected refund. It is not sent anywhere and does not change balances."""
    execution = get_execution(conn, workspace_id, execution_id)
    currency = str(execution["recipient_currency"])
    value = parse_amount(amount, currency)
    if value <= 0 or value > Decimal(str(execution["recipient_amount"])):
        raise DomainError(422, "invalid_amount", "A refund must be more than zero and at most the amount paid.")
    refund_id = new_id("rfd")
    conn.execute(
        "INSERT INTO refunds (id, workspace_id, execution_id, amount, currency, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (refund_id, workspace_id, execution_id, to_string(value, currency), currency, reason, iso(now)),
    )
    log_event(conn, workspace_id, now, "refund_recorded", "refund", refund_id, amount=to_string(value, currency), currency=currency)
    return get_execution(conn, workspace_id, execution_id)
