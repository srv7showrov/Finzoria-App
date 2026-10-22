from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import repositories as repo
from app.config import load_settings
from app.db import Database
from app.main import SESSION_COOKIE, create_app
from app.money import MoneyError, parse_amount, parse_decimal, to_string

from .conftest import ORIGIN, make_settings, start


def test_health_reports_database_and_unavailable_ai(client_factory) -> None:
    body = client_factory().get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"]["schema_version"] == 6
    assert body["ai"]["state"] == "unavailable"
    assert body["ai"]["missing"] == ["FINZORIA_ANTHROPIC_API_KEY", "FINZORIA_ANTHROPIC_MODEL"]


def test_session_cookie_is_httponly_and_reused(client_factory) -> None:
    client = client_factory()
    first = client.post("/api/session", headers=ORIGIN)
    cookie = first.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    second = client.post("/api/session", headers=ORIGIN)
    assert second.json() == {"workspace_id": first.json()["workspace_id"], "created": False}


def test_secure_cookie_when_configured(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, cookie_secure=True))) as client:
        response = client.post("/api/session", headers={"Origin": "http://testserver"})
        assert "secure" in response.headers["set-cookie"].lower()


def test_private_routes_require_session(client_factory) -> None:
    client = client_factory()
    for path in ("/api/session", "/api/profile", "/api/preferences", "/api/accounts"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "no_session"


def test_sample_workspace_has_profile_preferences_and_opening_balances(client_factory) -> None:
    client = client_factory()
    start(client)
    assert client.get("/api/profile").json()["display_name"] == "Demo Student"
    prefs = client.get("/api/preferences").json()
    assert (prefs["language"], prefs["display_currency"], prefs["time_zone"]) == ("en", "BDT", "Asia/Dhaka")
    accounts = client.get("/api/accounts").json()["accounts"]
    assert [(a["currency"], a["opening_balance"]) for a in accounts] == [("BDT", "100000.00"), ("AUD", "0.00")]


def test_account_order_is_explicit_and_stable(client_factory) -> None:
    # Seeded accounts share a created_at and have random IDs; order must come from position.
    for _ in range(25):
        client = client_factory()
        start(client)
        currencies = [a["currency"] for a in client.get("/api/accounts").json()["accounts"]]
        assert currencies == ["BDT", "AUD"]


def test_position_backfill_keeps_insertion_order(tmp_path: Path, monkeypatch) -> None:
    import app.db as db_module

    v1_only = tmp_path / "migrations"
    v1_only.mkdir()
    (v1_only / "0001_foundation.sql").write_text(
        (db_module.MIGRATIONS_DIR / "0001_foundation.sql").read_text(encoding="utf-8"), encoding="utf-8"
    )
    real_dir = db_module.MIGRATIONS_DIR
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", v1_only)
    db = Database(tmp_path / "old.sqlite3")
    assert db.migrate() == 1
    with db.transaction() as conn:
        conn.execute("INSERT INTO workspaces (id, created_at) VALUES ('ws_old', 't')")
        # Inserted AUD first with a lexically larger id and identical created_at.
        for acct_id, currency in (("acct_z", "AUD"), ("acct_a", "BDT")):
            conn.execute(
                "INSERT INTO accounts (id, workspace_id, name, currency, opening_balance, opening_date, created_at)"
                " VALUES (?, 'ws_old', ?, ?, '0.00', '2026-10-19', 't')",
                (acct_id, currency, currency),
            )
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", real_dir)
    assert db.migrate() == 6
    with db.read() as conn:
        assert [a["currency"] for a in repo.list_accounts(conn, "ws_old")] == ["AUD", "BDT"]


def test_preferences_update_rejects_read_only_fields(client_factory) -> None:
    """Regression for the onboarding 422: the API stays strict; the client must send only editable fields."""
    client = client_factory()
    start(client)
    current = client.get("/api/preferences").json()
    assert "updated_at" in current
    full = {**current, "language": "bn"}
    rejected = client.put("/api/preferences", json=full, headers=ORIGIN)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["fields"][0]["field"] == "updated_at"
    editable = {k: full[k] for k in ("language", "display_currency", "time_zone")}
    accepted = client.put("/api/preferences", json=editable, headers=ORIGIN)
    assert accepted.status_code == 200 and accepted.json()["language"] == "bn"


def test_workspaces_are_isolated(client_factory) -> None:
    alice, bob = client_factory(), client_factory()
    start(alice)
    start(bob)
    alice.put(
        "/api/preferences",
        json={"language": "ar", "display_currency": "AUD", "time_zone": "Australia/Sydney"},
        headers=ORIGIN,
    ).raise_for_status()
    alice.put("/api/profile", json={"display_name": "Alice", "institution": ""}, headers=ORIGIN).raise_for_status()

    assert bob.get("/api/preferences").json()["language"] == "en"
    assert bob.get("/api/profile").json()["display_name"] == "Demo Student"

    alice_ids = {a["id"] for a in alice.get("/api/accounts").json()["accounts"]}
    bob_ids = {a["id"] for a in bob.get("/api/accounts").json()["accounts"]}
    assert alice_ids.isdisjoint(bob_ids)
    foreign_id = next(iter(alice_ids))
    # An ID from another workspace never grants access.
    response = bob.get(f"/api/accounts/{foreign_id}")
    assert response.status_code == 404
    assert alice.get(f"/api/accounts/{foreign_id}").status_code == 200


def test_preferences_survive_reload_and_backend_restart(settings) -> None:
    with TestClient(create_app(settings), base_url="http://localhost:8000") as client:
        start(client)
        client.put(
            "/api/preferences",
            json={"language": "de", "display_currency": "EUR", "time_zone": "Europe/Berlin"},
            headers=ORIGIN,
        ).raise_for_status()
        client.put("/api/profile", json={"display_name": "Mina", "institution": "Uni"}, headers=ORIGIN)
        token = client.cookies[SESSION_COOKIE]
        # Reload: a fresh request with the same cookie.
        assert client.get("/api/preferences").json()["language"] == "de"

    # Restart: a brand-new application instance over the same database file.
    with TestClient(create_app(settings), base_url="http://localhost:8000") as restarted:
        restarted.cookies.set(SESSION_COOKIE, token)
        prefs = restarted.get("/api/preferences").json()
        assert (prefs["language"], prefs["display_currency"], prefs["time_zone"]) == ("de", "EUR", "Europe/Berlin")
        assert restarted.get("/api/profile").json()["display_name"] == "Mina"
        assert len(restarted.get("/api/accounts").json()["accounts"]) == 2


def test_expired_session_is_rejected(settings, client_factory) -> None:
    client = client_factory()
    start(client)
    db = Database(settings.database_path)
    with db.transaction() as conn:
        conn.execute("UPDATE sessions SET expires_at = ?", (repo.iso(repo.utc_now() - timedelta(seconds=1)),))
    assert client.get("/api/preferences").status_code == 401


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "https://evil.example"}, {"Referer": "https://evil.example/page"}, {"Origin": "null"}],
)
def test_mutations_from_other_origins_are_rejected(client_factory, headers) -> None:
    client = client_factory()
    start(client)
    response = client.put(
        "/api/preferences",
        json={"language": "de", "display_currency": "EUR", "time_zone": "Europe/Berlin"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_rejected"
    assert client.get("/api/preferences").json()["language"] == "en"


def test_no_permissive_cors_headers(client_factory) -> None:
    response = client_factory().get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "payload",
    [
        {"language": "fr", "display_currency": "BDT", "time_zone": "Asia/Dhaka"},
        {"language": "en", "display_currency": "XYZ", "time_zone": "Asia/Dhaka"},
        {"language": "en", "display_currency": "BDT", "time_zone": "Mars/Base"},
        {"language": "en", "display_currency": "BDT", "time_zone": "Asia/Dhaka", "nationality": "BD"},
    ],
)
def test_invalid_preferences_are_rejected_without_echo(client_factory, payload) -> None:
    client = client_factory()
    start(client)
    response = client.put("/api/preferences", json=payload, headers=ORIGIN)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "Mars/Base" not in response.text and "XYZ" not in response.text
    assert client.get("/api/preferences").json()["language"] == "en"


def test_unknown_api_route_is_json_404(client_factory) -> None:
    response = client_factory().get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_frontend_serving_blocks_path_traversal(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    with TestClient(create_app(make_settings(tmp_path, frontend_dist=dist))) as client:
        assert client.get("/budget").text == "<html>app</html>"
        assert "secret" not in client.get("/../secret.txt").text
        assert "secret" not in client.get("/%2e%2e/secret.txt").text


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "m.sqlite3")
    assert db.migrate() == 6
    assert db.migrate() == 6


# --- money primitives ------------------------------------------------------------


def test_decimal_strings_parse_exactly() -> None:
    assert parse_decimal("0.1") + parse_decimal("0.2") == Decimal("0.3")
    assert to_string(parse_amount("100000", "BDT"), "BDT") == "100000.00"
    assert to_string(parse_amount("1500", "JPY"), "JPY") == "1500"


@pytest.mark.parametrize("value", ["1e5", "NaN", "Infinity", "", "1,000", "12.3.4", " ", "0x10"])
def test_invalid_decimal_strings_are_rejected(value: str) -> None:
    with pytest.raises(MoneyError):
        parse_decimal(value)


def test_amount_rules() -> None:
    with pytest.raises(MoneyError):
        parse_decimal(1.5)  # type: ignore[arg-type]
    with pytest.raises(MoneyError):
        parse_amount("-1.00", "BDT")
    with pytest.raises(MoneyError):
        parse_amount("10.5", "JPY")
    with pytest.raises(MoneyError):
        parse_amount("1.001", "AUD")
    with pytest.raises(MoneyError):
        parse_amount("1.00", "XYZ")


# --- settings isolation from developer-tool credentials ---------------------------


def test_settings_ignore_generic_anthropic_variables(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-be-used")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://tool-proxy.invalid")
    for name in ("FINZORIA_ANTHROPIC_API_KEY", "FINZORIA_ANTHROPIC_MODEL", "FINZORIA_ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings(tmp_path / "missing.env")
    assert settings.anthropic_api_key is None
    assert settings.anthropic_base_url == "https://api.anthropic.com"
    assert "should-not-be-used" not in repr(settings)


def test_settings_read_ignored_env_file(tmp_path: Path, monkeypatch) -> None:
    for name in ("FINZORIA_ANTHROPIC_API_KEY", "FINZORIA_ANTHROPIC_MODEL"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("FINZORIA_ANTHROPIC_API_KEY=test-key\nFINZORIA_ANTHROPIC_MODEL=test-model\n", encoding="utf-8")
    settings = load_settings(env)
    assert settings.anthropic_api_key == "test-key" and settings.anthropic_model == "test-model"
    assert "test-key" not in repr(settings)
