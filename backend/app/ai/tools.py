"""Allowlisted assistant tools. Every tool:

- validates its arguments with a Pydantic model (unknown fields rejected),
- runs against the session's workspace (model-supplied IDs are looked up inside that
  workspace only, so a foreign ID is simply "not found"),
- calls the same services as the screens (no separate arithmetic),
- returns a concise JSON result for the model and a card for the UI.

Preparation tools never save financial changes. prepare_budget_change, prepare_bill and
prepare_contribution create a *pending action* the user must confirm in the UI;
prepare_payment creates a payment proposal in "ready_for_review", which still needs the
existing explicit, versioned approval and execution flow. There is no tool that approves,
executes, records received money or deletes anything.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..db import Database
from ..errors import DomainError
from ..money import MoneyError, parse_amount, to_string, validate_currency
from ..services import budget, cashflow, funding, ledger, payments, rates, reports
from ..services.common import iso, log_event, new_id, parse_date
from ..services.dashboard import dashboard

MAX_RESULT_CHARS = 8000
MAX_PLANNED_ENTRIES = 20

IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Month = Annotated[str, Field(pattern=r"^\d{4}-\d{2}$")]
Amount = Annotated[str, Field(pattern=r"^\d{1,15}(\.\d{1,8})?$", description="Decimal string such as \"1250.00\"")]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Ref = Annotated[str, Field(min_length=1, max_length=64)]


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PeriodArgs(ToolArgs):
    month: Month | None = Field(default=None, description="Calendar month YYYY-MM. Defaults to the current month.")
    start: IsoDate | None = Field(default=None, description="Custom range start (YYYY-MM-DD); needs end.")
    end: IsoDate | None = Field(default=None, description="Custom range end (YYYY-MM-DD), inclusive.")


class BudgetArgs(PeriodArgs):
    entry_kind: Literal["income", "expense"] | None = Field(default=None, description="Only list planned entries of this kind.")
    entry_search: Annotated[str, Field(max_length=40)] | None = Field(
        default=None, description="Case-insensitive text matched against the planned entry's description or category, e.g. \"rent\".")


class ConvertArgs(ToolArgs):
    amount: Amount
    from_currency: Currency
    to_currency: Currency


class QuotesArgs(ToolArgs):
    bill_id: Ref
    source_account_id: Ref | None = Field(default=None, description="Defaults to the account with the reserve floor.")


class ScenarioArgs(ToolArgs):
    type: Literal["delay_contribution", "change_expense"]
    contribution_id: Ref | None = None
    new_date: IsoDate | None = None
    entry_id: Ref | None = Field(default=None, description="ID of an existing planned expense, taken from calculate_budget's "
                                 "planned_entries. Never guess it.")
    new_amount: Amount | None = None
    month: Month | None = None


class BudgetChangeArgs(ToolArgs):
    kind: Literal["income", "expense"]
    category: Annotated[str, Field(pattern=r"^[a-z0-9_]{1,40}$")]
    description: Annotated[str, Field(max_length=200)] = ""
    amount: Amount
    currency: Currency
    start_date: IsoDate
    recurrence: Literal["none", "monthly"]
    end_date: IsoDate | None = None


class BillArgs(ToolArgs):
    description: Annotated[str, Field(min_length=1, max_length=120)]
    payee: Annotated[str, Field(min_length=1, max_length=120)]
    category: Literal["tuition", "campus", "housing", "other"] = "tuition"
    amount: Amount
    currency: Currency
    due_date: IsoDate


class ContributionArgs(ToolArgs):
    contributor: Annotated[str, Field(min_length=1, max_length=80)]
    amount: Amount
    expected_date: IsoDate
    certainty: Literal["expected", "uncertain"] = "expected"
    account_id: Ref | None = Field(default=None, description="Defaults to the account with the reserve floor.")


class PaymentArgs(ToolArgs):
    bill_id: Ref
    route: Literal["A", "B", "C"]
    source_account_id: Ref | None = None


class StatusArgs(ToolArgs):
    action_id: Ref | None = Field(default=None, description="ID of a pending action prepared earlier.")
    proposal_id: Ref | None = Field(default=None, description="ID of a payment proposal.")


@dataclass(frozen=True)
class ToolContext:
    workspace_id: str
    db: Database
    today: date
    now: datetime
    display_currency: str
    conversation_id: str | None


@dataclass(frozen=True)
class ToolOutcome:
    ok: bool
    data: dict[str, object]
    card: dict[str, object] | None = None


class ToolError(Exception):
    """A user-correctable problem reported back to the model as an error result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- helpers -----------------------------------------------------------------------


def _period(ctx: ToolContext, args: PeriodArgs) -> budget.Period:
    return budget.resolve_period(args.month, args.start, args.end, ctx.today)


def _default_account(conn, ctx: ToolContext, account_id: str | None) -> str:  # type: ignore[no-untyped-def]
    if account_id:
        ledger.get_account_row(conn, ctx.workspace_id, account_id)  # workspace-scoped; foreign IDs -> not found
        return account_id
    reserve = funding.get_reserve(conn, ctx.workspace_id)
    if reserve:
        return str(reserve["account_id"])
    accounts = ledger.balances(conn, ctx.workspace_id)
    if not accounts:
        raise ToolError("no_account", "This workspace has no accounts.")
    return str(accounts[0]["id"])


def _create_action(conn, ctx: ToolContext, kind: str, payload: dict[str, object]) -> str:  # type: ignore[no-untyped-def]
    action_id = new_id("act")
    conn.execute(
        "INSERT INTO assistant_actions (id, workspace_id, conversation_id, kind, payload, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
        (action_id, ctx.workspace_id, ctx.conversation_id, kind, json.dumps(payload, sort_keys=True), iso(ctx.now), iso(ctx.now)),
    )
    log_event(conn, ctx.workspace_id, ctx.now, "assistant_action_prepared", "assistant_action", action_id, kind=kind)
    return action_id


def _pending(kind: str, action_id: str, payload: dict[str, object]) -> ToolOutcome:
    note = "Prepared only. Nothing is saved until the user presses Confirm on this card in the app."
    return ToolOutcome(True, {"action_id": action_id, "status": "pending_user_confirmation", "kind": kind,
                              "details": payload, "note": note},
                       {"type": "pending_action", "action_id": action_id, "kind": kind, "payload": payload, "status": "pending"})


# --- read-only tools ---------------------------------------------------------------


def read_financial_summary(ctx: ToolContext, args: PeriodArgs) -> ToolOutcome:
    with ctx.db.read() as conn:
        d = dashboard(conn, ctx.workspace_id, _period(ctx, args), ctx.display_currency, ctx.today)
        contributions = [c for c in funding.list_contributions(conn, ctx.workspace_id) if c["status"] == "expected"]
    data = {
        "today": d["today"], "period": d["period"], "display_currency": d["display_currency"],
        "actual_balances": [{k: a[k] for k in ("id", "name", "currency", "balance")} for a in d["balances"]],  # type: ignore[union-attr]
        "budget": d["budget"], "forecast_not_available_cash": d["forecast"], "reserve": d["reserve"],
        "open_bills": [{k: b[k] for k in ("id", "description", "payee", "amount", "currency", "due_date", "overdue")}
                       for b in d["upcoming_bills"]],  # type: ignore[union-attr]
        "expected_contributions_not_received": [{k: c[k] for k in ("id", "contributor", "amount", "currency", "expected_date", "certainty")}
                                                for c in contributions],
        "funding": d["funding"],
        "goals": [{k: g[k] for k in ("name", "target_amount", "allocated_amount", "currency", "progress_percent")} for g in d["goals"]],  # type: ignore[union-attr]
        "rates_used": d["valuation"],
    }
    return ToolOutcome(True, data, {"type": "summary", **{k: data[k] for k in ("actual_balances", "budget", "forecast_not_available_cash",
                                                                                "reserve", "open_bills", "display_currency")}})


def _planned_entries(conn, ctx: ToolContext, period: budget.Period, args: BudgetArgs) -> tuple[list[dict[str, object]], int]:  # type: ignore[no-untyped-def]
    """Existing planning entries of this workspace with at least one occurrence in the period,
    optionally filtered, so the model can refer to them by their real IDs. Bounded."""
    needle = (args.entry_search or "").casefold()
    matches: list[dict[str, object]] = []
    for e in budget.list_entries(conn, ctx.workspace_id):
        if args.entry_kind and e["kind"] != args.entry_kind:
            continue
        if needle and needle not in f"{e['description']} {e['category']}".casefold():
            continue
        dates = budget.occurrences(e, period.start, period.end)
        if not dates:
            continue
        matches.append({**{k: e[k] for k in ("id", "kind", "category", "description", "amount", "currency", "recurrence",
                                             "start_date", "end_date")},
                        "occurrences_in_period": [d.isoformat() for d in dates[:5]]})
    return matches[:MAX_PLANNED_ENTRIES], len(matches)


def calculate_budget(ctx: ToolContext, args: BudgetArgs) -> ToolOutcome:
    period = _period(ctx, args)
    with ctx.db.read() as conn:
        s = budget.summary(conn, ctx.workspace_id, period, ctx.display_currency)
        entries, total = _planned_entries(conn, ctx, period, args)
    data = {k: s[k] for k in ("period", "display_currency", "planned_income", "planned_expenses", "planned_remainder",
                              "actual_income", "actual_expenses", "actual_net", "categories", "complete", "unconverted_count", "valuation")}
    card = {"type": "budget", **data}
    data["planned_entries"] = entries
    data["planned_entries_total"] = total
    data["planned_entries_note"] = ("Existing planning entries (original currency). Use these IDs for run_scenario "
                                    "change_expense; if several match the user's description, ask which one.")
    return ToolOutcome(True, data, card)


def convert_currency(ctx: ToolContext, args: ConvertArgs) -> ToolOutcome:
    value = parse_amount(args.amount, validate_currency(args.from_currency))
    validate_currency(args.to_currency)
    with ctx.db.read() as conn:
        rate = rates.get_rate(conn, ctx.workspace_id, args.from_currency, args.to_currency)
    data = {"amount": to_string(value, args.from_currency), "from": args.from_currency, "to": args.to_currency,
            "result": to_string(rates.convert(value, rate), args.to_currency), "rate": rate.as_dict(),
            "note": "Fixture or manual planning rate; not an executable provider quote."}
    return ToolOutcome(True, data, {"type": "conversion", **data})


def compare_quotes(ctx: ToolContext, args: QuotesArgs) -> ToolOutcome:
    with ctx.db.read() as conn:
        account_id = _default_account(conn, ctx, args.source_account_id)
        result = payments.compare_routes(conn, ctx.workspace_id, args.bill_id, account_id, ctx.today)
    result["note"] = "Routes A, B and C are fictional demonstrations; timings are calendar days under demo assumptions."
    return ToolOutcome(True, result, {"type": "quotes", **result})


def run_scenario(ctx: ToolContext, args: ScenarioArgs) -> ToolOutcome:
    with ctx.db.read() as conn:
        period = budget.resolve_period(args.month, None, None, ctx.today)
        result = cashflow.run_scenario(conn, ctx.workspace_id, ctx.today, period, ctx.display_currency, args.model_dump())

    def brief(p: dict[str, object]) -> dict[str, object]:
        return {k: p[k] for k in ("from", "to", "current_funds", "projected_end_confirmed", "projected_end_with_expected",
                                  "lowest_confirmed", "lowest_with_expected", "reserve_floor", "display_currency")}

    data: dict[str, object] = {"type": result["type"], "saved": False, "authorizes_payment": False,
                               "baseline": brief(result["baseline"]), "scenario": brief(result["scenario"])}  # type: ignore[arg-type]
    if "payment_timing" in result:
        data["payment_timing"] = result["payment_timing"]
        data["assumption"] = result.get("assumption")
    # The card keeps "type": "scenario" for the UI; the scenario kind goes in scenario_type.
    return ToolOutcome(True, data, {**data, "type": "scenario", "scenario_type": data["type"]})


def generate_report_summary(ctx: ToolContext, args: PeriodArgs) -> ToolOutcome:
    with ctx.db.read() as conn:
        r = reports.report(conn, ctx.workspace_id, _period(ctx, args), ctx.display_currency, ctx.today)
    data = {k: r[k] for k in ("period", "display_currency", "totals", "categories", "funding", "transfer_fees", "goals",
                              "complete", "unconverted_count", "valuation")}
    return ToolOutcome(True, data, {"type": "report", **{k: data[k] for k in ("period", "display_currency", "totals", "transfer_fees")}})


def get_action_status(ctx: ToolContext, args: StatusArgs) -> ToolOutcome:
    if not (args.action_id or args.proposal_id):
        raise ToolError("missing_id", "Give action_id or proposal_id.")
    with ctx.db.read() as conn:
        if args.action_id:
            row = conn.execute("SELECT id, kind, status, result_id, status_reason FROM assistant_actions"
                               " WHERE workspace_id = ? AND id = ?", (ctx.workspace_id, args.action_id)).fetchone()
            if row is None:
                raise ToolError("not_found", "No such action in this workspace.")
            data: dict[str, object] = dict(row)
        else:
            p = payments.get_proposal(conn, ctx.workspace_id, str(args.proposal_id), ctx.now)
            data = {"proposal_id": p["id"], "status": p["status"], "version": p["version"],
                    "execution": p["execution"] and {k: p["execution"][k] for k in ("receipt_number", "total_debit", "balance_after",  # type: ignore[index]
                                                                                     "source_currency", "executed_at", "simulated")}}
    return ToolOutcome(True, data, {"type": "status", **data})


# --- preparation tools (no financial change is saved) -------------------------------


def prepare_budget_change(ctx: ToolContext, args: BudgetChangeArgs) -> ToolOutcome:
    validate_currency(args.currency)
    if parse_amount(args.amount, args.currency) <= 0:
        raise ToolError("invalid_amount", "Amount must be greater than zero.")
    start = parse_date(args.start_date, "start_date")
    if args.end_date and parse_date(args.end_date, "end_date") < start:
        raise ToolError("invalid_period", "end_date must be on or after start_date.")
    payload = args.model_dump()
    with ctx.db.transaction() as conn:
        action_id = _create_action(conn, ctx, "budget_entry", payload)
    return _pending("budget_entry", action_id, payload)


def prepare_bill(ctx: ToolContext, args: BillArgs) -> ToolOutcome:
    validate_currency(args.currency)
    if parse_amount(args.amount, args.currency) <= 0:
        raise ToolError("invalid_amount", "Amount must be greater than zero.")
    parse_date(args.due_date, "due_date")
    payload = args.model_dump()
    with ctx.db.transaction() as conn:
        action_id = _create_action(conn, ctx, "bill", payload)
    return _pending("bill", action_id, payload)


def prepare_contribution(ctx: ToolContext, args: ContributionArgs) -> ToolOutcome:
    with ctx.db.transaction() as conn:
        account_id = _default_account(conn, ctx, args.account_id)
        currency = ledger.get_account_row(conn, ctx.workspace_id, account_id)["currency"]
        if parse_amount(args.amount, currency) <= 0:
            raise ToolError("invalid_amount", "Amount must be greater than zero.")
        parse_date(args.expected_date, "expected_date")
        payload = {**args.model_dump(), "account_id": account_id, "currency": currency}
        action_id = _create_action(conn, ctx, "contribution", payload)
    return _pending("contribution", action_id, payload)


def prepare_payment(ctx: ToolContext, args: PaymentArgs) -> ToolOutcome:
    with ctx.db.transaction() as conn:
        account_id = _default_account(conn, ctx, args.source_account_id)
        p = payments.create_proposal(conn, ctx.workspace_id, args.bill_id, account_id, args.route, ctx.now, ctx.today)
    terms = p["terms"]
    data = {
        "proposal_id": p["id"], "status": p["status"], "version": p["version"], "simulated": True,
        "terms": {k: terms[k] for k in ("recipient", "recipient_amount", "recipient_currency", "source_currency", "principal", "fee",  # type: ignore[index]
                                        "total_debit", "estimated_arrival", "on_time")},
        "rate": terms["rate"], "expires_at": terms["quote"]["expires_at"],  # type: ignore[index]
        "checks": p["checks"],
        "note": "This is a proposal only. The user must review and approve this exact version in Payments, then run the "
                "simulated payment. The assistant cannot approve or execute it.",
    }
    return ToolOutcome(True, data, {"type": "payment_proposal", **data})


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[ToolArgs]
    run: Callable[[ToolContext, ToolArgs], ToolOutcome]  # type: ignore[type-arg]


TOOLS: dict[str, Tool] = {t.name: t for t in (
    Tool("read_financial_summary", "Current actual balances, budget totals, cash-flow forecast (not available cash), reserve floor, "
         "open bills, expected contributions not yet received and goals for a period.", PeriodArgs, read_financial_summary),  # type: ignore[arg-type]
    Tool("calculate_budget", "Planned versus actual income and spending for a month or custom range, valued in the display "
         "currency, by category, plus the existing planned entries in that period (ID, kind, category, description, "
         "amount, currency, recurrence, dates), optionally filtered by kind or text.", BudgetArgs, calculate_budget),  # type: ignore[arg-type]
    Tool("convert_currency", "Convert an amount with the workspace's stored fixture or manual rates, including provenance. "
         "Fails for pairs without a rate.", ConvertArgs, convert_currency),  # type: ignore[arg-type]
    Tool("compare_quotes", "Compare the three fictional demo routes A/B/C for paying an open bill: amounts, fees, arrival, "
         "funds and reserve-floor checks.", QuotesArgs, compare_quotes),  # type: ignore[arg-type]
    Tool("run_scenario", "What-if only (nothing saved): delay an expected contribution (with payment timing per route) or "
         "change the amount of an EXISTING planned expense (entry_id from calculate_budget).", ScenarioArgs, run_scenario),  # type: ignore[arg-type]
    Tool("prepare_budget_change", "Prepare a new planning entry for the user to confirm. Does not save it.", BudgetChangeArgs,
         prepare_budget_change),  # type: ignore[arg-type]
    Tool("prepare_bill", "Prepare a tuition/campus bill for the user to review and confirm. Does not save it.", BillArgs,
         prepare_bill),  # type: ignore[arg-type]
    Tool("prepare_contribution", "Prepare an EXPECTED contribution for the user to confirm. It cannot mark money as received.",
         ContributionArgs, prepare_contribution),  # type: ignore[arg-type]
    Tool("prepare_payment", "Create a simulated payment proposal (ready for the user's review) for an open bill and route. "
         "Cannot approve or execute.", PaymentArgs, prepare_payment),  # type: ignore[arg-type]
    Tool("get_action_status", "Status of a prepared action or payment proposal.", StatusArgs, get_action_status),  # type: ignore[arg-type]
    Tool("generate_report_summary", "Period report totals, categories, funding gap, transfer fees and goals (same figures as "
         "the dashboard).", PeriodArgs, generate_report_summary),  # type: ignore[arg-type]
)}


def _schema(model: type[ToolArgs]) -> dict[str, object]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():  # type: ignore[union-attr]
        prop.pop("title", None)
    return schema


def tool_definitions() -> list[dict[str, object]]:
    return [{"name": t.name, "description": t.description, "input_schema": _schema(t.args)} for t in TOOLS.values()]


def _clip(data: dict[str, object]) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return json.dumps({"truncated": True, "partial": text[:MAX_RESULT_CHARS]}, ensure_ascii=False)


def execute(ctx: ToolContext, name: str, raw_input: object) -> tuple[str, str, ToolOutcome]:
    """Run one tool call. Returns (status, validated-input JSON, outcome). Never raises for
    model mistakes: unknown tools, invalid arguments and domain errors become error results."""
    tool = TOOLS.get(name)
    if tool is None:
        return "rejected", "{}", ToolOutcome(False, {"error": "unknown_tool",
                                                     "message": f"'{name}' is not an available tool. Approving or executing "
                                                                "payments is only possible by the user in the app."})
    try:
        args = tool.args.model_validate(raw_input if isinstance(raw_input, dict) else {})
    except ValidationError as exc:
        fields = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return "rejected", "{}", ToolOutcome(False, {"error": "invalid_arguments", "fields": fields})
    validated = args.model_dump_json()
    try:
        return "ok", validated, tool.run(ctx, args)
    except ToolError as exc:
        return "error", validated, ToolOutcome(False, {"error": exc.code, "message": exc.message})
    except DomainError as exc:
        return "error", validated, ToolOutcome(False, {"error": exc.code, "message": exc.message})
    except MoneyError as exc:
        return "error", validated, ToolOutcome(False, {"error": "invalid_amount", "message": str(exc)})


def result_text(outcome: ToolOutcome) -> str:
    return _clip(outcome.data)
