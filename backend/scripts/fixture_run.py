"""Deterministic fixture run (no AI model) for release evidence.

Replays the demo fixed scenario through the HTTP API on a throw-away database with
the 2026-10-19 simulation clock and writes a sanitized log of expected-versus-actual
figures, approval-rejection cases and the route cost comparison to
docs/evidence/fixture-run.md. It measures only what it runs; it is not AI evidence.

    python scripts/fixture_run.py      (from backend/, with the venv interpreter)

Exit code 0 when every expectation matched, 1 otherwise.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.clock import SimulationClock  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.main import create_app  # noqa: E402

ORIGIN = {"Origin": "http://localhost:5173"}
EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "fixture-run.md"
FIXTURE_START = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)


class Log:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, bool]] = []
        self.rejections: list[tuple[str, str, str, bool]] = []

    def expect(self, name: str, expected: object, actual: object) -> None:
        self.rows.append((name, str(expected), str(actual), str(expected) == str(actual)))

    def reject(self, case: str, response: Any, expected_status: int, expected_code: str) -> None:
        code = (response.json().get("error") or {}).get("code") if response.status_code >= 400 else "accepted"
        self.rejections.append((case, f"{expected_status} {expected_code}", f"{response.status_code} {code}",
                                response.status_code == expected_status and code == expected_code))


def post(c: TestClient, path: str, body: dict[str, object] | None = None) -> Any:
    return c.post(path, json=body or {}, headers=ORIGIN)


def bdt(c: TestClient) -> dict[str, Any]:
    return next(a for a in c.get("/api/accounts").json()["accounts"] if a["currency"] == "BDT")


def run(c: TestClient, other: TestClient, log: Log) -> None:
    summary = c.get("/api/budget/summary?month=2026-10").json()
    log.expect("Arithmetic fixture: planned remainder (BDT)", "12500.00", summary["planned_remainder"])
    mixed = c.get("/api/rates/convert", params={"amount": "20", "from": "USD", "to": "AUD"}).json()
    log.expect("Mixed-currency fixture: USD 20 -> AUD", "30.00", mixed["result"])
    log.expect("Opening BDT balance", "100000.00", bdt(c)["balance"])

    bill = c.get("/api/bills").json()["bills"][0]
    account = bdt(c)["id"]
    routes = {r["route"]: r for r in c.get(f"/api/bills/{bill['id']}/routes", params={"source_account_id": account}).json()["routes"]}
    for code, total, after in (("A", "81000.00", "19000.00"), ("B", "81500.00", "18500.00"), ("C", "80500.00", "19500.00")):
        log.expect(f"Route {code} total debit today", total, routes[code]["total_debit"])
        log.expect(f"Route {code} balance after", after, routes[code]["balance_after"])
    log.expect("Route A gap to floor", "-1000.00", routes["A"]["gap_to_floor"])
    log.expect("Route C on time (arrives 2026-10-27)", "False", routes["C"]["on_time"])

    contribution = c.get("/api/contributions").json()["contributions"][0]
    delay = post(c, "/api/scenarios", {"type": "delay_contribution", "contribution_id": contribution["id"],
                                       "new_date": "2026-10-24"}).json()
    delayed = {r["route"]: r for t in delay["payment_timing"] if t["case"] == "scenario" for r in t["routes"]}
    log.expect("Delay to 10-24: route A arrival", "2026-10-26", delayed["A"]["estimated_arrival"])
    log.expect("Delay to 10-24: route B arrival", "2026-10-25", delayed["B"]["estimated_arrival"])
    log.expect("Delay scenario saved nothing (balance)", "100000.00", bdt(c)["balance"])

    proposal = post(c, "/api/payments/proposals", {"bill_id": bill["id"], "route": "A", "source_account_id": account}).json()
    approve = {"version": proposal["version"], "terms_hash": proposal["terms_hash"]}
    log.reject("Approve route A before the contribution (reserve floor)",
               post(c, f"/api/payments/proposals/{proposal['id']}/approve", approve), 409, "reserve_breach")
    log.reject("Execute without approval", post(c, f"/api/payments/proposals/{proposal['id']}/execute",
                                                 {"idempotency_key": "fixture-0001"}), 409, "not_approved")
    log.reject("Another workspace approves this proposal",
               post(other, f"/api/payments/proposals/{proposal['id']}/approve", approve), 404, "not_found")
    log.reject("Client-supplied amount on a proposal",
               post(c, "/api/payments/proposals", {"bill_id": bill["id"], "route": "A", "source_account_id": account,
                                                   "total_debit": "1.00"}), 422, "validation_error")

    post(c, f"/api/contributions/{contribution['id']}/receive")
    second = post(c, f"/api/contributions/{contribution['id']}/receive").json()
    log.expect("Balance after contribution (received twice, credited once)", "110000.00", bdt(c)["balance"])
    log.expect("Second receive credited", "False", second.get("credited"))

    log.reject("Approve a stale version", post(c, f"/api/payments/proposals/{proposal['id']}/approve",
                                                {"version": proposal["version"] + 5, "terms_hash": proposal["terms_hash"]}),
               409, "terms_changed")
    current = c.get(f"/api/payments/proposals/{proposal['id']}").json()
    approved = post(c, f"/api/payments/proposals/{proposal['id']}/approve",
                    {"version": current["version"], "terms_hash": current["terms_hash"]}).json()
    log.expect("Explicit approval status", "approved", approved.get("status"))
    first = post(c, f"/api/payments/proposals/{proposal['id']}/execute", {"idempotency_key": "fixture-0002"}).json()
    retry = post(c, f"/api/payments/proposals/{proposal['id']}/execute", {"idempotency_key": "fixture-0003"}).json()
    log.expect("Execution status", "executed_simulated", first.get("status"))
    log.expect("Retry replays the first execution", "True", retry.get("replayed"))
    log.expect("Final BDT balance", "29000.00", bdt(c)["balance"])
    log.expect("Executions", "1", len(c.get("/api/payments/executions").json()["executions"]))
    log.expect("Tuition bill status", "settled", c.get("/api/bills").json()["bills"][0]["status"])
    report = c.get("/api/reports?month=2026-10").json()
    dash = c.get("/api/dashboard?month=2026-10").json()
    log.expect("Report actual expenses = dashboard", dash["budget"]["actual_expenses"], report["totals"]["actual_expenses"])
    log.expect("Report transfer fees (BDT)", "1000.00", report["transfer_fees"]["total"])


def render(log: Log, routes_note: str) -> str:
    ok_rows = sum(r[3] for r in log.rows)
    ok_rej = sum(r[3] for r in log.rejections)
    lines = [f"# Deterministic fixture run — {datetime.now(UTC).strftime('%Y-%m-%dT%H:%MZ')}", "",
             "No AI model involved. Fictional data, simulation clock 2026-10-19 09:00 Asia/Dhaka, temporary database. "
             "Generated by `backend/scripts/fixture_run.py`.", "",
             f"**Calculation outputs matching the fixture:** {ok_rows}/{len(log.rows)}  ",
             f"**Approval/permission rejections behaving as specified:** {ok_rej}/{len(log.rejections)}", "",
             "## Expected versus actual", "", "| Check | Expected | Actual | Result |", "|---|---|---|---|",
             *[f"| {n} | {e} | {a} | {'PASS' if p else 'FAIL'} |" for n, e, a, p in log.rows], "",
             "## Rejection cases", "", "| Case | Expected | Actual | Result |", "|---|---|---|---|",
             *[f"| {n} | {e} | {a} | {'PASS' if p else 'FAIL'} |" for n, e, a, p in log.rejections], "",
             "## Cost comparison against the fixture baseline", "", routes_note, ""]
    return "\n".join(lines)


def main() -> int:
    settings = load_settings()
    settings = type(settings)(**{**settings.__dict__, "database_path": Path(tempfile.mkdtemp()) / "fixture.sqlite3",
                                 "anthropic_api_key": None, "anthropic_model": None})
    app = create_app(settings)
    log = Log()
    with TestClient(app, base_url="http://localhost:8000") as c, TestClient(app, base_url="http://localhost:8000") as other:
        app.state.clock = SimulationClock(FIXTURE_START)
        post(c, "/api/session").raise_for_status()
        post(other, "/api/session").raise_for_status()
        run(c, other, log)
    note = ("Fixture baseline: deliver AUD 1,000.00 at 0.0125 AUD/BDT = BDT 80,000.00 principal. Fictional route totals: "
            "A BDT 81,000.00 (fee 1,000.00), B 81,500.00 (fee 1,500.00), C 80,500.00 (fee 500.00, late). The cheapest on-time "
            "route after the contribution is A: BDT 500.00 less than B. C is cheaper but misses the 2026-10-25 due date. "
            "These are demonstration routes, not market quotes.")
    EVIDENCE.write_text(render(log, note), encoding="utf-8")
    passed = all(r[3] for r in log.rows + log.rejections)
    print(("PASSED" if passed else "FAILED") + f": fixture run; evidence at {EVIDENCE}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
