"""Real, low-token connection check for the selected provider (FINZORIA_AI_PROVIDER:
gemini or anthropic). Makes exactly ONE small model request.

Run from the backend folder with the virtual environment interpreter:
    python scripts/ai_smoke_test.py

Exit codes: 0 = PASSED (usable text reply), 1 = FAILED, 2 = NOT RUN (not configured or local guard),
3 = CONNECTED BUT NO USABLE TEXT (the authenticated request worked but returned no text, e.g. the
output budget was used by thinking; connectivity is proven, a usable reply is not).
The result is stored (sanitized) so /api/health can report it. No key is printed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import repositories as repo  # noqa: E402
from app.ai import usage  # noqa: E402
from app.ai.adapter import build_adapter  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.db import Database  # noqa: E402


def main() -> int:
    settings = load_settings()
    adapter = build_adapter(settings)
    if not adapter.configured:
        print(f"NOT RUN: provider={adapter.provider}; missing " + ", ".join(adapter.missing_configuration()) + " in backend/.env")
        return 2
    db = Database(settings.database_path)
    db.migrate()
    with db.read() as conn:
        blocked = usage.blocked_by(conn, adapter)
    if blocked:
        print(f"NOT RUN: local guard {blocked} reached (this app's own request count); try later.")
        return 2
    print(f"Sending one model request (provider={adapter.provider}, model={adapter.model})...", flush=True)
    result = adapter.smoke_test()
    reached = result.ok or result.outcome in ("connected_no_text", "refusal", "malformed_response")
    usage.record(db, workspace_id=None, provider=adapter.provider, model=str(adapter.model), purpose="check",
                 ok=reached, error_code=None if result.ok else result.outcome)
    with db.transaction() as conn:
        repo.record_ai_check(conn, adapter.model or "", result.ok, result.outcome)
    label = "PASSED" if result.ok else "CONNECTED BUT NO USABLE TEXT" if result.outcome == "connected_no_text" else "FAILED"
    print(f"{label}: one real API request, provider={adapter.provider}, model={adapter.model}, outcome={result.outcome}"
          f"{', ' + result.details if result.details else ''}, model requests sent=1", flush=True)
    if result.ok:
        return 0
    return 3 if result.outcome == "connected_no_text" else 1


if __name__ == "__main__":
    raise SystemExit(main())
