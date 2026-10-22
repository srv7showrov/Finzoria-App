"""Adapter behaviour with a MOCK client. These tests never contact the API and
are not evidence of a working language-model connection; the real check is
scripts/ai_smoke_test.py."""

from __future__ import annotations

from types import SimpleNamespace

import anthropic
import httpx2
from fastapi.testclient import TestClient

from app import repositories as repo
from app.ai.adapter import AnthropicAdapter, connection_status
from app.db import Database
from app.main import create_app

from .conftest import make_settings


class MockMessages:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def adapter_with(tmp_path, outcome: object) -> tuple[AnthropicAdapter, MockMessages]:
    adapter = AnthropicAdapter(make_settings(tmp_path, anthropic_api_key="k", anthropic_model="m"))
    messages = MockMessages(outcome)
    adapter._client = SimpleNamespace(messages=messages)  # type: ignore[assignment]
    return adapter, messages


def test_unconfigured_adapter_does_not_call(tmp_path) -> None:
    adapter = AnthropicAdapter(make_settings(tmp_path))
    result = adapter.smoke_test()
    assert (result.ok, result.outcome) == (False, "not_configured")


def test_mock_success_is_low_token(tmp_path) -> None:
    reply = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="ready")])
    adapter, messages = adapter_with(tmp_path, reply)
    assert adapter.smoke_test().ok
    assert messages.calls[0]["max_tokens"] == 64
    assert messages.calls[0]["model"] == "m"


def test_mock_authentication_error_is_sanitized(tmp_path) -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(401, request=request, json={"error": {"message": "secret detail"}})
    error = anthropic.AuthenticationError("secret detail", response=response, body=None)
    adapter, _ = adapter_with(tmp_path, error)
    result = adapter.smoke_test()
    assert (result.ok, result.outcome) == (False, "authentication_error")


def test_mock_connection_error(tmp_path) -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    adapter, _ = adapter_with(tmp_path, anthropic.APIConnectionError(request=request))
    assert adapter.smoke_test().outcome == "connection_error"


def test_client_uses_explicit_key_and_base_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://tool-proxy.invalid")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tool-token")
    adapter = AnthropicAdapter(make_settings(tmp_path, anthropic_api_key="app-key", anthropic_model="m"))
    client = adapter.client()
    assert str(client.base_url).startswith("https://api.anthropic.com")
    assert client.api_key == "app-key"
    assert client.auth_token is None


def test_status_states(tmp_path) -> None:
    adapter = AnthropicAdapter(make_settings(tmp_path, anthropic_api_key="k", anthropic_model="m"))
    assert connection_status(adapter, None)["state"] == "configured_unverified"
    ok = {"checked_at": "t", "model": "m", "ok": True, "outcome": "ok"}
    assert connection_status(adapter, ok)["state"] == "connected"
    assert connection_status(adapter, {**ok, "ok": False})["state"] == "failed"
    # A check recorded for a different model does not count.
    assert connection_status(adapter, {**ok, "model": "other"})["state"] == "configured_unverified"


def test_health_never_exposes_key(tmp_path) -> None:
    settings = make_settings(tmp_path, anthropic_api_key="sk-test-secret", anthropic_model="m")
    with TestClient(create_app(settings)) as client:
        with Database(settings.database_path).transaction() as conn:
            repo.record_ai_check(conn, "m", True, "ok")
        response = client.get("/api/health")
        assert response.json()["ai"]["state"] == "connected"
        assert "sk-test-secret" not in response.text
        assert "sk-test-secret" not in client.get("/api/ai/status").text
