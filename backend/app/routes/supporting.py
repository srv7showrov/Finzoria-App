"""Student funding, reports, deadline notices and calendar export.
Every handler is scoped to the session's workspace through Ctx."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response

from ..deps import Ctx
from ..money import validate_currency
from ..schemas import ChecklistUpdate, FundingApplicationIn, WorkIncomeIn
from ..services import budget, notices, reports, student

router = APIRouter(prefix="/api")

MonthQ = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]
DateQ = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")]
CurrencyQ = Annotated[str | None, Query(min_length=3, max_length=3)]


def _report(ctx: Ctx, month: str | None, start: str | None, end: str | None, currency: str | None) -> dict[str, object]:
    period = budget.resolve_period(month, start, end, ctx.today())
    display = validate_currency(currency) if currency else ctx.display_currency
    with ctx.db.read() as conn:
        return reports.report(conn, ctx.workspace_id, period, display, ctx.today())


# --- funding ----------------------------------------------------------------------


@router.get("/funding")
def get_funding(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return student.overview(conn, ctx.workspace_id, ctx.today())


@router.post("/funding/applications")
def post_application(body: FundingApplicationIn, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return student.create_application(conn, ctx.workspace_id, now=ctx.now(), **body.model_dump())


@router.put("/funding/applications/{app_id}")
def put_application(app_id: str, body: FundingApplicationIn, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return student.update_application(conn, ctx.workspace_id, app_id, now=ctx.now(), **body.model_dump())


@router.delete("/funding/applications/{app_id}")
def delete_application(app_id: str, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        student.delete_application(conn, ctx.workspace_id, app_id, ctx.now())
    return {"deleted": True}


@router.put("/funding/checklist/{item_key}")
def put_checklist(item_key: str, body: ChecklistUpdate, ctx: Ctx) -> dict[str, object]:
    with ctx.db.transaction() as conn:
        return student.set_checklist_item(conn, ctx.workspace_id, item_key, body.done, ctx.now())


@router.post("/funding/work-income")
def post_work_income(body: WorkIncomeIn, ctx: Ctx) -> dict[str, object]:
    return student.work_income(**body.model_dump())


# --- reports ------------------------------------------------------------------------


@router.get("/reports")
def get_report(ctx: Ctx, month: MonthQ = None, start: DateQ = None, end: DateQ = None,
               currency: CurrencyQ = None) -> dict[str, object]:
    return _report(ctx, month, start, end, currency)


@router.get("/reports/export.csv")
def get_report_csv(ctx: Ctx, month: MonthQ = None, start: DateQ = None, end: DateQ = None,
                   currency: CurrencyQ = None) -> Response:
    data = _report(ctx, month, start, end, currency)
    period = data["period"]
    name = f"finzoria-report-{period['start']}-{period['end']}.csv"  # type: ignore[index]
    return Response(
        content="﻿" + reports.report_csv(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Content-Type-Options": "nosniff"},
    )


# --- notices and calendar -------------------------------------------------------------


@router.get("/notices")
def get_notices(ctx: Ctx) -> dict[str, object]:
    with ctx.db.read() as conn:
        return notices.notices(conn, ctx.workspace_id, ctx.today())


@router.get("/calendar.ics")
def get_calendar(ctx: Ctx) -> Response:
    with ctx.db.read() as conn:
        body = notices.calendar_ics(conn, ctx.workspace_id, ctx.time_zone, ctx.now())
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="finzoria-deadlines.ics"', "X-Content-Type-Options": "nosniff"},
    )
