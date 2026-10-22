"""Stage C / Prompt 5: student funding, reports, notices, calendar export and workspace data
controls, under the 2026-10-19 simulation clock with the demo fixture."""

from __future__ import annotations

import csv
import io

import pytest

from app.services.reports import safe_cell

from .conftest import ORIGIN, balance_of, bdt_account, ok


def post(client, path, body):  # type: ignore[no-untyped-def]
    return client.post(path, json=body, headers=ORIGIN)


# --- reports ------------------------------------------------------------------------


def test_report_totals_match_dashboard_and_budget_summary(sim) -> None:
    c = sim.client()
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    ok(post(c, f"/api/contributions/{contribution['id']}/receive", {}))
    for params in ("month=2026-10", "month=2026-10&currency=AUD", "start=2026-10-01&end=2026-12-31"):
        report = ok(c.get(f"/api/reports?{params}"))
        summary = ok(c.get(f"/api/budget/summary?{params}"))
        dash = ok(c.get(f"/api/dashboard?{params}"))
        for key in ("planned_income", "planned_expenses", "planned_remainder", "actual_income", "actual_expenses", "actual_net"):
            assert report["totals"][key] == summary[key], (params, key)
        assert report["funding"] == dash["funding"]
        assert report["forecast"] == dash["forecast"]
        assert report["goals"] == dash["goals"]
        assert report["valuation"] == summary["valuation"]


def test_report_counts_transfer_fees_after_simulated_payment(sim) -> None:
    c = sim.client()
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    ok(post(c, f"/api/contributions/{contribution['id']}/receive", {}))
    bill = ok(c.get("/api/bills"))["bills"][0]
    proposal = ok(post(c, "/api/payments/proposals", {"bill_id": bill["id"], "route": "A",
                                                      "source_account_id": bdt_account(c)}))
    ok(post(c, f"/api/payments/proposals/{proposal['id']}/approve",
            {"version": proposal["version"], "terms_hash": proposal["terms_hash"]}))
    ok(post(c, f"/api/payments/proposals/{proposal['id']}/execute", {"idempotency_key": "report-fee-0001"}))
    report = ok(c.get("/api/reports?month=2026-10"))
    assert report["transfer_fees"]["total"] == "1000.00"
    assert [f["amount"] for f in report["transfer_fees"]["items"]] == ["1000.00"]
    assert balance_of(c) == "29000.00"


@pytest.mark.parametrize("text", ["=HYPERLINK(\"http://x\")", "+1+2", "-2+3", "@SUM(A1)", "\tcmd", "\rcmd"])
def test_safe_cell_neutralises_formulas(text: str) -> None:
    assert safe_cell(text).startswith("'")


def test_safe_cell_keeps_plain_numbers() -> None:
    assert safe_cell("-1000.00") == "-1000.00"
    assert safe_cell("29000.00") == "29000.00"


def test_csv_export_protects_formulas_in_user_text(sim) -> None:
    c = sim.client()
    ok(post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "expense", "category": "food",
                                     "amount": "10.00", "description": "=cmd|' /C calc'!A0", "occurred_on": "2026-10-19"}))
    r = c.get("/api/reports/export.csv?month=2026-10")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
    cells = [cell for row in rows for cell in row]
    assert "'=cmd|' /C calc'!A0" in cells
    assert not any(cell.startswith(("=", "+", "@")) for cell in cells)
    actual = [row for row in rows if row[0] == "actual" and row[4].endswith("A0")][0]
    assert actual[5] == "-10.00"  # numbers stay numbers


# --- funding ----------------------------------------------------------------------


def test_applications_crud_and_validation(sim) -> None:
    c = sim.client()
    created = ok(post(c, "/api/funding/applications", {"name": "Faculty bursary (demo)", "provider": "Demo University",
                                                       "deadline": "2026-10-28"}))
    assert created["status"] == "planning"
    updated = ok(c.put(f"/api/funding/applications/{created['id']}", json={"name": "Faculty bursary (demo)",
                                                                          "status": "applied", "deadline": "2026-10-28"}, headers=ORIGIN))
    assert updated["status"] == "applied"
    assert post(c, "/api/funding/applications", {"name": "X", "status": "guaranteed"}).status_code == 422
    assert post(c, "/api/funding/applications", {"name": "X", "deadline": "2026-02-30"}).status_code == 422
    assert post(c, "/api/funding/applications", {"name": "X", "amount": "5000"}).status_code == 422
    assert [a["id"] for a in ok(c.get("/api/funding"))["applications"]] == [created["id"]]
    assert ok(c.delete(f"/api/funding/applications/{created['id']}", headers=ORIGIN))["deleted"] is True
    assert ok(c.get("/api/funding"))["applications"] == []


def test_checklist_state_is_allowlisted(sim) -> None:
    c = sim.client()
    data = ok(c.put("/api/funding/checklist/credit_au.free_report", json={"done": True}, headers=ORIGIN))
    credit = next(g for g in data["groups"] if g["key"] == "credit_au")
    assert next(i for i in credit["items"] if i["key"] == "credit_au.free_report")["done"] is True
    assert c.put("/api/funding/checklist/anything.else", json={"done": True}, headers=ORIGIN).status_code == 404


def test_resources_are_official_links_marked_unverified(sim) -> None:
    c = sim.client()
    data = ok(c.get("/api/funding"))
    assert data["checked"] == {"date": "2026-10-19", "status": "not_verified", "reason": "network_blocked"}
    assert all(r["url"].startswith("https://www.") or r["url"].startswith("https://moneysmart.gov.au") for r in data["resources"])
    assert all(".gov.au" in r["url"] for r in data["resources"])
    for r in data["resources"]:
        assert set(r) == {"key", "url", "kind", "jurisdiction"}  # no amounts or deadlines


def test_work_income_calculator(sim) -> None:
    c = sim.client()
    gross = ok(post(c, "/api/funding/work-income", {"hourly_rate": "25.50", "hours_per_week": "20", "weeks": 4,
                                                    "currency": "AUD", "basis": "gross", "deduction_percent": "12.5"}))
    assert (gross["weekly_gross"], gross["weekly_net"], gross["total_gross"], gross["total_net"], gross["deductions_total"]) == \
        ("510.00", "446.25", "2040.00", "1785.00", "255.00")
    net = ok(post(c, "/api/funding/work-income", {"hourly_rate": "22.00", "hours_per_week": "15", "weeks": 2,
                                                  "currency": "AUD", "basis": "net", "deduction_percent": "30"}))
    assert (net["total_net"], net["total_gross"], net["deduction_percent"]) == ("660.00", None, "0")
    jpy = ok(post(c, "/api/funding/work-income", {"hourly_rate": "1100", "hours_per_week": "10.5", "weeks": 1,
                                                  "currency": "JPY", "basis": "gross", "deduction_percent": "0"}))
    assert jpy["total_net"] == "11550"
    for bad in ({"hourly_rate": 25.5}, {"hourly_rate": "0"}, {"hours_per_week": "81"}, {"weeks": 0},
                {"deduction_percent": "100"}, {"currency": "XYZ"}, {"basis": "after_tax"}, {"hourly_rate": "NaN"}):
        body = {"hourly_rate": "25.50", "hours_per_week": "20", "weeks": 4, "currency": "AUD", "basis": "gross",
                "deduction_percent": "10", **bad}
        assert post(c, "/api/funding/work-income", body).status_code == 422, bad


# --- notices and calendar -------------------------------------------------------------


def test_notices_and_calendar_are_date_only(sim) -> None:
    c = sim.client()
    ok(post(c, "/api/funding/applications", {"name": "Bursary; with, commas\nand newline", "deadline": "2026-10-30"}))
    notices = ok(c.get("/api/notices"))
    assert notices["background"] is False
    kinds = {(n["kind"], n["date"], n["days"]) for n in notices["notices"]}
    assert ("bill", "2026-10-25", 6) in kinds
    assert ("contribution", "2026-10-20", 1) in kinds
    assert ("application", "2026-10-30", 11) in kinds
    r = c.get("/api/calendar.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    assert "X-WR-TIMEZONE:Asia/Dhaka" in body
    assert "DTSTART;VALUE=DATE:20261025\r\n" in body and "DTEND;VALUE=DATE:20261026\r\n" in body
    assert "DTSTART:2026" not in body  # no timed events
    assert "Bursary\\; with\\, commas\\nand newline" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))


def test_settled_bills_leave_notices(sim) -> None:
    c = sim.client()
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    ok(post(c, f"/api/contributions/{contribution['id']}/receive", {}))
    assert not any(n["kind"] == "contribution" for n in ok(c.get("/api/notices"))["notices"])


# --- workspace data controls ------------------------------------------------------------


def test_export_contains_only_own_workspace_and_no_session_hashes(sim) -> None:
    alice, bob = sim.client(), sim.client()
    ok(post(bob, "/api/funding/applications", {"name": "Bob only"}))
    r = alice.get("/api/workspace/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["format"] == "finzoria-workspace-export"
    assert "sessions" not in data["tables"]
    assert "Bob only" not in r.text and "token_hash" not in r.text
    assert len(data["tables"]["accounts"]) == 2
    assert all("workspace_id" not in row for rows in data["tables"].values() for row in rows)


def test_reset_requires_confirmation_and_only_affects_own_workspace(sim) -> None:
    alice, bob = sim.client(), sim.client()
    ok(post(bob, "/api/funding/applications", {"name": "Bob keeps this"}))
    ok(alice.put("/api/preferences", json={"language": "de", "display_currency": "AUD", "time_zone": "Australia/Sydney"},
                 headers=ORIGIN))
    contribution = ok(alice.get("/api/contributions"))["contributions"][0]
    ok(post(alice, f"/api/contributions/{contribution['id']}/receive", {}))
    assert balance_of(alice) == "110000.00"
    assert post(alice, "/api/workspace/reset", {}).status_code == 422
    assert post(alice, "/api/workspace/reset", {"confirm": "reset"}).status_code == 422
    assert alice.post("/api/workspace/reset", json={"confirm": "RESET"}).status_code == 403  # no Origin
    assert balance_of(alice) == "110000.00"
    old_ws = ok(alice.get("/api/session"))["workspace_id"]
    ok(post(alice, "/api/workspace/reset", {"confirm": "RESET"}))
    assert ok(alice.get("/api/session"))["workspace_id"] != old_ws
    assert balance_of(alice) == "100000.00"
    prefs = ok(alice.get("/api/preferences"))
    assert (prefs["language"], prefs["display_currency"], prefs["time_zone"]) == ("de", "AUD", "Australia/Sydney")
    assert [a["name"] for a in ok(bob.get("/api/funding"))["applications"]] == ["Bob keeps this"]


def test_delete_requires_confirmation_removes_everything_and_ends_session(sim) -> None:
    alice, bob = sim.client(), sim.client()
    ws = ok(alice.get("/api/session"))["workspace_id"]
    assert post(alice, "/api/workspace/delete", {"confirm": "RESET"}).status_code == 422
    ok(post(alice, "/api/workspace/delete", {"confirm": "DELETE"}))
    assert alice.get("/api/accounts").status_code == 401
    with sim.db.read() as conn:
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            if "workspace_id" in cols:
                assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id = ?", (ws,)).fetchone()[0] == 0, table
    assert balance_of(bob) == "100000.00"


def test_supporting_records_are_workspace_scoped(sim) -> None:
    alice, bob = sim.client(), sim.client()
    app = ok(post(alice, "/api/funding/applications", {"name": "Alice only", "deadline": "2026-10-22"}))
    assert bob.put(f"/api/funding/applications/{app['id']}", json={"name": "x"}, headers=ORIGIN).status_code == 404
    assert bob.delete(f"/api/funding/applications/{app['id']}", headers=ORIGIN).status_code == 404
    assert not any(n["title"] == "Alice only" for n in ok(bob.get("/api/notices"))["notices"])
    assert "Alice only" not in bob.get("/api/calendar.ics").text
    assert ok(alice.get("/api/funding"))["applications"][0]["name"] == "Alice only"


# --- CSV signed converted values ---------------------------------------------------------


def _csv_rows(c, params):  # type: ignore[no-untyped-def]
    r = c.get(f"/api/reports/export.csv?{params}")
    assert r.status_code == 200
    return list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))


def _pay_tuition_route_a(c) -> None:  # type: ignore[no-untyped-def]
    bill = ok(c.get("/api/bills"))["bills"][0]
    proposal = ok(post(c, "/api/payments/proposals", {"bill_id": bill["id"], "route": "A", "source_account_id": bdt_account(c)}))
    ok(post(c, f"/api/payments/proposals/{proposal['id']}/approve", {"version": proposal["version"], "terms_hash": proposal["terms_hash"]}))
    ok(post(c, f"/api/payments/proposals/{proposal['id']}/execute", {"idempotency_key": "csv-sign-0001"}))


def test_csv_converted_values_carry_the_sign_of_the_original(sim) -> None:
    from decimal import Decimal

    c = sim.client()
    ok(post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "expense", "category": "food",
                                     "amount": "100.00", "description": "Groceries", "occurred_on": "2026-10-19"}))
    contribution = ok(c.get("/api/contributions"))["contributions"][0]
    ok(post(c, f"/api/contributions/{contribution['id']}/receive", {}))
    _pay_tuition_route_a(c)
    rows = _csv_rows(c, "month=2026-10&currency=AUD")
    header = rows[1]
    assert header[7] == "value_AUD"
    actual = {r[4] or r[2]: r for r in rows if r[0] == "actual"}
    groceries = next(r for r in rows if r[0] == "actual" and r[4] == "Groceries")
    assert (groceries[5], groceries[6], groceries[7]) == ("-100.00", "BDT", "-1.25")  # the reported defect
    fee = next(r for r in rows if r[0] == "actual" and r[2] == "fee")
    assert (fee[5], fee[6], fee[7]) == ("-1000.00", "BDT", "-12.50")
    payment = next(r for r in rows if r[0] == "actual" and r[2] == "payment")
    assert (payment[5], payment[7]) == ("-80000.00", "-1000.00")
    credit = next(r for r in rows if r[0] == "actual" and r[5] == "10000.00")
    assert (credit[6], credit[7]) == ("BDT", "125.00")
    assert actual  # every actual row: sign of value matches sign of amount
    for r in (r for r in rows if r[0] == "actual"):
        assert r[7].startswith("-") == r[5].startswith("-"), r
    report = ok(c.get("/api/reports?month=2026-10&currency=AUD"))
    assert report["complete"] is True
    assert sum(Decimal(r[7]) for r in rows if r[0] == "actual") == Decimal(report["totals"]["actual_net"])
    # Totals rows and the shared unsigned display amounts are unchanged.
    totals = {r[2]: r[5] for r in rows if r[0] == "total"}
    assert totals["actual_expenses"] == report["totals"]["actual_expenses"] and not totals["actual_expenses"].startswith("-")
    assert all(not str(i["display_amount"]).startswith("-") for i in report["actual_items"])


def test_csv_same_currency_and_missing_rate_values(sim) -> None:
    from decimal import Decimal

    c = sim.client()
    ok(post(c, "/api/transactions", {"account_id": bdt_account(c), "kind": "expense", "category": "food",
                                     "amount": "100.00", "description": "Groceries", "occurred_on": "2026-10-19"}))
    rows = _csv_rows(c, "month=2026-10&currency=BDT")
    groceries = next(r for r in rows if r[0] == "actual" and r[4] == "Groceries")
    assert (groceries[5], groceries[7]) == ("-100.00", "-100.00")
    report = ok(c.get("/api/reports?month=2026-10&currency=BDT"))
    assert sum(Decimal(r[7]) for r in rows if r[0] == "actual") == Decimal(report["totals"]["actual_net"])
    eur = _csv_rows(c, "month=2026-10&currency=EUR")  # no BDT->EUR rate in the fixture
    groceries = next(r for r in eur if r[0] == "actual" and r[4] == "Groceries")
    assert (groceries[5], groceries[7]) == ("-100.00", "")
