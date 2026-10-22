"""Bills and the reviewed, approved, simulated payment workflow.

Approval is only reachable from this explicit endpoint, called by the session's own
UI action. There is no route that approves or executes on anyone else's behalf.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..deps import Ctx
from ..errors import DomainError
from ..schemas import BillBody, ProposalApprove, ProposalCreate, ProposalExecute, RefundCreate
from ..services import bills, payments

router = APIRouter(prefix="/api")


def _raise_if_failed(result: dict[str, object]) -> dict[str, object]:
    """Some outcomes (expired, failed) must persist their status before the error is returned."""
    error = result.get("error")
    if isinstance(error, DomainError):
        raise error
    return result


@router.get("/bills")
def get_bills(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"bills": bills.list_bills(conn, ctx.workspace_id)}


@router.post("/bills")
def post_bill(body: BillBody, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return bills.create_bill(conn, ctx.workspace_id, now=ctx.now(), **body.model_dump())


@router.put("/bills/{bill_id}")
def put_bill(bill_id: str, body: BillBody, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return bills.update_bill(conn, ctx.workspace_id, bill_id, now=ctx.now(), **body.model_dump())


@router.get("/bills/{bill_id}/routes")
def get_routes(bill_id: str, ctx: Ctx, source_account_id: str = Query(max_length=64)) -> dict[str, object]:
    with ctx.db.read() as conn:
        return payments.compare_routes(conn, ctx.workspace_id, bill_id, source_account_id, ctx.today())


@router.get("/payments/proposals")
def get_proposals(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"proposals": payments.list_proposals(conn, ctx.workspace_id, ctx.now())}


@router.post("/payments/proposals")
def post_proposal(body: ProposalCreate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return payments.create_proposal(conn, ctx.workspace_id, body.bill_id, body.source_account_id, body.route,
                                        ctx.now(), ctx.today())


@router.get("/payments/proposals/{proposal_id}")
def get_proposal(proposal_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return payments.get_proposal(conn, ctx.workspace_id, proposal_id, ctx.now())


@router.post("/payments/proposals/{proposal_id}/approve")
def approve(proposal_id: str, body: ProposalApprove, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        result = payments.approve(conn, ctx.workspace_id, proposal_id, body.version, body.terms_hash, ctx.now())
    return _raise_if_failed(result)


@router.post("/payments/proposals/{proposal_id}/execute")
def execute(proposal_id: str, body: ProposalExecute, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        result = payments.execute(conn, ctx.workspace_id, proposal_id, body.idempotency_key, ctx.now(), ctx.today())
    return _raise_if_failed(result)


@router.post("/payments/proposals/{proposal_id}/cancel")
def cancel(proposal_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return payments.cancel(conn, ctx.workspace_id, proposal_id, ctx.now())


@router.post("/payments/proposals/{proposal_id}/refresh")
def refresh(proposal_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return payments.refresh(conn, ctx.workspace_id, proposal_id, ctx.now(), ctx.today())


@router.get("/payments/executions")
def get_executions(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"executions": payments.list_executions(conn, ctx.workspace_id)}


@router.get("/payments/executions/status")
def get_execution_status(ctx: Ctx, idempotency_key: str = Query(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")) -> dict[str, object]:
    with ctx.db.read() as conn:
        return payments.execution_status(conn, ctx.workspace_id, idempotency_key)


@router.get("/payments/executions/{execution_id}")
def get_execution(execution_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return payments.get_execution(conn, ctx.workspace_id, execution_id)


@router.post("/payments/executions/{execution_id}/refunds")
def post_refund(execution_id: str, body: RefundCreate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return payments.record_refund(conn, ctx.workspace_id, execution_id, body.amount, body.reason, ctx.now())
