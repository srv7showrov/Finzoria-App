"""AI Financial Workspace endpoints. The model only reads data and prepares items; the
confirm endpoints below are the user's explicit UI actions."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..ai import actions, assistant, invoice
from ..deps import Ctx
from ..schemas import ChatRequest, InvoiceText

router = APIRouter(prefix="/api/assistant")


def _turn_context(ctx: Ctx) -> assistant.TurnContext:
    return assistant.TurnContext(ctx.workspace_id, ctx.db, ctx.today(), ctx.now(), ctx.display_currency, ctx.language,
                                 ctx.time_zone)


@router.post("/chat")
def chat(body: ChatRequest, ctx: Ctx, request: Request) -> dict[str, object]:
    return assistant.run_turn(request.app.state.ai, _turn_context(ctx), body.conversation_id, body.message, body.mode)


@router.get("/conversations")
def conversations(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"conversations": assistant.list_conversations(conn, ctx.workspace_id)}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return assistant.conversation_detail(conn, ctx.workspace_id, conversation_id)


@router.get("/actions")
def pending_actions(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"actions": [a for a in actions.list_actions(conn, ctx.workspace_id) if a["status"] == "pending"]}


@router.post("/actions/{action_id}/confirm")
def confirm(action_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return actions.confirm(conn, ctx.workspace_id, action_id, ctx.now(), ctx.today())


@router.post("/actions/{action_id}/dismiss")
def dismiss(action_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return actions.dismiss(conn, ctx.workspace_id, action_id, ctx.now())


@router.post("/invoice/extract")
def extract_invoice(body: InvoiceText, ctx: Ctx, request: Request) -> dict[str, object]:
    # Session required. Extraction stores no financial data; it only logs the request attempt.
    return invoice.extract(request.app.state.ai, body.text, ctx.db, ctx.workspace_id)
