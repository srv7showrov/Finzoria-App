from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ORIGIN = {"Origin": "http://localhost:5173"}


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_path": tmp_path / "test.sqlite3",
        "frontend_dist": tmp_path / "no-dist",
        "allowed_origins": ("http://localhost:5173",),
        "cookie_secure": False,
        "session_days": 14,
        "anthropic_api_key": None,
        "anthropic_model": None,
        "anthropic_base_url": "https://api.anthropic.com",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def client_factory(settings: Settings) -> Iterator[Callable[[], TestClient]]:
    """Each call gives an independent browser-like client against the same database."""
    clients: list[TestClient] = []
    app = create_app(settings)

    def make() -> TestClient:
        client = TestClient(app, base_url="http://localhost:8000")
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def start(client: TestClient) -> str:
    response = client.post("/api/session", headers=ORIGIN)
    assert response.status_code == 200, response.text
    return str(response.json()["workspace_id"])


# --- simulation clock for the demo fixtures (2026-10-19, Asia/Dhaka) ---------

from datetime import UTC, datetime  # noqa: E402

from app.clock import SimulationClock  # noqa: E402

FIXTURE_START = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)  # 09:00 in Asia/Dhaka


class Sim:
    """An app with a fixed simulation clock plus helpers to open independent sessions."""

    def __init__(self, settings: Settings) -> None:
        self.clock = SimulationClock(FIXTURE_START)
        self.app = create_app(settings)
        self.app.state.clock = self.clock
        self.db = self.app.state.db
        self._clients: list[TestClient] = []

    def client(self) -> TestClient:
        client = TestClient(self.app, base_url="http://localhost:8000")
        client.__enter__()
        self.app.state.clock = self.clock  # lifespan does not reset it, but keep it explicit
        self._clients.append(client)
        start(client)
        return client

    def close(self) -> None:
        for client in self._clients:
            client.__exit__(None, None, None)


@pytest.fixture
def sim(settings: Settings) -> Iterator[Sim]:
    s = Sim(settings)
    yield s
    s.close()


def ok(response) -> dict:  # type: ignore[no-untyped-def]
    assert response.status_code == 200, response.text
    return response.json()


def balance_of(client: TestClient, currency: str = "BDT") -> str:
    accounts = ok(client.get("/api/accounts"))["accounts"]
    return next(a["balance"] for a in accounts if a["currency"] == currency)


def bdt_account(client: TestClient) -> str:
    return next(a["id"] for a in ok(client.get("/api/accounts"))["accounts"] if a["currency"] == "BDT")
