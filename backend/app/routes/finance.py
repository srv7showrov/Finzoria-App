"""Budget, cash flow, contributions, goals, reserve, rates and dashboard endpoints.
Every handler is scoped to the session's workspace through Ctx."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from ..deps import Ctx
from ..money import parse_amount, to_string, validate_currency
from ..schemas import (
    BudgetEntryCreate,
    ContributionCreate,
    ContributionReceive,
    GoalAllocation,
    GoalCreate,
    ManualRateCreate,
    OccurrenceRecord,
    RateScenario,
    RateTargetCreate,
    ReserveUpdate,
    Scenario,
    TransactionCreate,
)
from ..services import budget, cashflow, funding, ledger, rates
from ..services.common import log_event, parse_date, recent_events, require_not_future
from ..services.dashboard import dashboard

router = APIRouter(prefix="/api")

# Annotated aliases (a shared Query() default object would make FastAPI drop repeated parameters).
MonthQ = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]
DateQ = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")]
CurrencyQ = Annotated[str | None, Query(min_length=3, max_length=3)]


def _display(ctx: Ctx, currency: str | None) -> str:
    return validate_currency(currency) if currency else ctx.display_currency


def _period(ctx: Ctx, month: str | None, start: str | None, end: str | None) -> budget.Period:
    return budget.resolve_period(month, start, end, ctx.today())


# --- dashboard and activity ------------------------------------------------------


@router.get("/dashboard")
def get_dashboard(ctx: Ctx, month: MonthQ = None, start: DateQ = None, end: DateQ = None,
                  currency: CurrencyQ = None) -> dict[str, object]:
    with ctx.db.read() as conn:
        return dashboard(conn, ctx.workspace_id, _period(ctx, month, start, end), _display(ctx, currency), ctx.today())


@router.get("/activity")
def get_activity(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"events": recent_events(conn, ctx.workspace_id, 100)}


# --- transactions and budget --------------------------------------------------------


@router.get("/transactions")
def get_transactions(ctx: Ctx, start: DateQ = None, end: DateQ = None) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"transactions": ledger.list_transactions(
            conn, ctx.workspace_id, parse_date(start, "start") if start else None, parse_date(end, "end") if end else None)}


@router.post("/transactions")
def post_transaction(body: TransactionCreate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        account = ledger.get_account_row(conn, ctx.workspace_id, body.account_id)
        amount = parse_amount(body.amount, account["currency"])
        occurred_on = require_not_future(parse_date(body.occurred_on, "occurred_on"), ctx.today(), "occurred_on")
        txn_id = ledger.post(conn, ctx.workspace_id, body.account_id, body.kind, amount, body.category, body.description,
                             occurred_on, ctx.now())
        log_event(conn, ctx.workspace_id, ctx.now(), f"transaction_{body.kind}", "transaction", txn_id,
                  amount=to_string(amount, account["currency"]), currency=account["currency"])
        return {"id": txn_id, "balances": ledger.balances(conn, ctx.workspace_id)}


@router.get("/budget/entries")
def get_entries(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"entries": budget.list_entries(conn, ctx.workspace_id)}


@router.post("/budget/entries")
def post_entry(body: BudgetEntryCreate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return budget.create_entry(conn, ctx.workspace_id, now=ctx.now(), **body.model_dump())


@router.post("/budget/entries/{entry_id}/record")
def record_occurrence(entry_id: str, body: OccurrenceRecord, ctx: Ctx) -> dict[str, object]:
    """Explicitly record one planned occurrence as paid/received (posts and links atomically)."""
    with ctx.db.transaction() as conn:
        transaction_id = budget.record_occurrence(
            conn, ctx.workspace_id, entry_id, parse_date(body.occurrence_date, "occurrence_date"), body.account_id,
            parse_date(body.occurred_on, "occurred_on"), ctx.today(), ctx.now())
        return {"transaction_id": transaction_id, "balances": ledger.balances(conn, ctx.workspace_id)}


@router.delete("/budget/entries/{entry_id}")
def delete_entry(entry_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        budget.delete_entry(conn, ctx.workspace_id, entry_id, ctx.now())
    return {"deleted": True}


@router.get("/budget/summary")
def get_summary(ctx: Ctx, month: MonthQ = None, start: DateQ = None, end: DateQ = None,
                currency: CurrencyQ = None) -> dict[str, object]:
    with ctx.db.read() as conn:
        return budget.summary(conn, ctx.workspace_id, _period(ctx, month, start, end), _display(ctx, currency))


@router.get("/cashflow")
def get_cashflow(ctx: Ctx, month: MonthQ = None, start: DateQ = None, end: DateQ = None,
                 currency: CurrencyQ = None) -> dict[str, object]:
    period = _period(ctx, month, start, end)
    with ctx.db.read() as conn:
        return cashflow.project(conn, ctx.workspace_id, ctx.today(), max(period.end, ctx.today()), _display(ctx, currency))


@router.post("/scenarios")
def post_scenario(body: Scenario, ctx: Ctx, month: MonthQ = None, start: DateQ = None,
                  end: DateQ = None, currency: CurrencyQ = None) -> dict[str, object]:
    # Read-only connection: scenarios cannot change records even by mistake.
    with ctx.db.read() as conn:
        return cashflow.run_scenario(conn, ctx.workspace_id, ctx.today(), _period(ctx, month, start, end),
                                     _display(ctx, currency), body.model_dump())


# --- contributions, goals and reserve ---------------------------------------------


@router.get("/contributions")
def get_contributions(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"contributions": funding.list_contributions(conn, ctx.workspace_id)}


@router.post("/contributions")
def post_contribution(body: ContributionCreate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return funding.create_contribution(conn, ctx.workspace_id, now=ctx.now(), **body.model_dump())


@router.post("/contributions/{contribution_id}/receive")
def receive_contribution(contribution_id: str, body: ContributionReceive, ctx: Ctx) -> dict[str, object]:
    received_on = parse_date(body.received_on, "received_on") if body.received_on else ctx.today()
    require_not_future(received_on, ctx.today(), "received_on")
    with ctx.db.transaction() as conn:
        contribution, changed = funding.receive_contribution(conn, ctx.workspace_id, contribution_id, received_on, ctx.now())
        return {"contribution": contribution, "credited": changed, "balances": ledger.balances(conn, ctx.workspace_id)}


@router.post("/contributions/{contribution_id}/cancel")
def cancel_contribution(contribution_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return funding.cancel_contribution(conn, ctx.workspace_id, contribution_id, ctx.now())


@router.get("/goals")
def get_goals(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"goals": funding.list_goals(conn, ctx.workspace_id)}


@router.post("/goals")
def post_goal(body: GoalCreate, ctx: Ctx) -> dict[str, object]:
    validate_currency(body.currency)
    with ctx.db.transaction() as conn:
        funding.create_goal(conn, ctx.workspace_id, now=ctx.now(), **body.model_dump())
        return {"goals": funding.list_goals(conn, ctx.workspace_id)}


@router.put("/goals/{goal_id}")
def put_goal(goal_id: str, body: GoalAllocation, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        funding.update_goal_allocation(conn, ctx.workspace_id, goal_id, body.allocated_amount, ctx.now())
        return {"goals": funding.list_goals(conn, ctx.workspace_id)}


@router.get("/reserve")
def get_reserve(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {"reserve": funding.get_reserve(conn, ctx.workspace_id)}


@router.put("/reserve")
def put_reserve(body: ReserveUpdate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return {"reserve": funding.set_reserve(conn, ctx.workspace_id, body.account_id, body.floor_amount, ctx.now())}


# --- rates ---------------------------------------------------------------------


@router.get("/rates")
def get_rates(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return {
            "snapshots": rates.list_snapshots(conn, ctx.workspace_id),
            "targets": rates.list_targets(conn, ctx.workspace_id, ctx.now()),
            "reference_provider": {"connected": False, "reason": "not_configured"},
        }


@router.post("/rates/manual")
def post_manual_rate(body: ManualRateCreate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        snapshot_id = rates.add_snapshot(conn, ctx.workspace_id, body.base, body.quote, body.rate, "manual",
                                         rates.MANUAL_SOURCE, ctx.now(), ctx.now())
        log_event(conn, ctx.workspace_id, ctx.now(), "manual_rate_added", "fx_snapshot", snapshot_id,
                  base=body.base, quote=body.quote, rate=body.rate)
        return {"id": snapshot_id, "snapshots": rates.list_snapshots(conn, ctx.workspace_id)}


@router.get("/rates/convert")
def get_convert(ctx: Ctx, amount: str = Query(max_length=32), from_currency: str = Query(alias="from", min_length=3, max_length=3),
                to_currency: str = Query(alias="to", min_length=3, max_length=3)) -> dict[str, object]:
    value = parse_amount(amount, validate_currency(from_currency))
    with ctx.db.read() as conn:
        rate = rates.get_rate(conn, ctx.workspace_id, from_currency, validate_currency(to_currency))
    return {"amount": to_string(value, from_currency), "from": from_currency, "to": to_currency,
            "result": to_string(rates.convert(value, rate), to_currency), "rate": rate.as_dict()}


@router.post("/rates/scenario")
def post_rate_scenario(body: RateScenario, ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return rates.rate_scenario(conn, ctx.workspace_id, body.base, body.quote, body.amount, body.change_percent)


@router.post("/rates/targets")
def post_target(body: RateTargetCreate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        rates.create_target(conn, ctx.workspace_id, body.base, body.quote, body.threshold, body.direction, ctx.now())
        return {"targets": rates.list_targets(conn, ctx.workspace_id, ctx.now())}


@router.delete("/rates/targets/{target_id}")
def delete_target(target_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        rates.delete_target(conn, ctx.workspace_id, target_id)
        return {"targets": rates.list_targets(conn, ctx.workspace_id, ctx.now())}
