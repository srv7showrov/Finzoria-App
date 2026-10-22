"""Runtime settings.

Values come from backend/.env (ignored by Git) and then from the process
environment. Only FINZORIA_* names are read, so the app never picks up
credentials that belong to developer tools running in the same shell.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

DEFAULT_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


def _int(value: str | None) -> int | None:
    """Positive integer setting; anything else (including 0) means "not set"."""
    try:
        number = int(value) if value is not None else 0
    except ValueError:
        return None
    return number if number > 0 else None


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: Path
    frontend_dist: Path
    allowed_origins: tuple[str, ...]
    cookie_secure: bool
    session_days: int
    anthropic_api_key: str | None = field(repr=False)
    anthropic_model: str | None
    anthropic_base_url: str
    # Provider selection. No automatic fallback between providers.
    ai_provider: str = "anthropic"
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str | None = None
    # Local request guards (counted from this app's own request log; they are not the
    # provider's quota). None means "no local guard".
    ai_requests_per_minute: int | None = None
    ai_requests_per_day: int | None = None
    ai_requests_per_turn: int | None = None


def load_settings(env_file: Path | None = None) -> Settings:
    file_values = dotenv_values(env_file or BACKEND_DIR / ".env")

    def get(name: str) -> str | None:
        value = os.environ.get(name)
        if value is None:
            value = file_values.get(name)
        return value.strip() if isinstance(value, str) and value.strip() else None

    db = get("FINZORIA_DATABASE_PATH")
    origins = get("FINZORIA_ALLOWED_ORIGINS")
    return Settings(
        database_path=Path(db) if db else BACKEND_DIR / "data" / "finzoria.sqlite3",
        frontend_dist=PROJECT_DIR / "frontend" / "dist",
        allowed_origins=tuple(o.strip().rstrip("/") for o in origins.split(",") if o.strip())
        if origins
        else DEFAULT_ORIGINS,
        cookie_secure=_bool(get("FINZORIA_COOKIE_SECURE"), False),
        session_days=int(get("FINZORIA_SESSION_DAYS") or "14"),
        anthropic_api_key=get("FINZORIA_ANTHROPIC_API_KEY"),
        anthropic_model=get("FINZORIA_ANTHROPIC_MODEL"),
        anthropic_base_url=get("FINZORIA_ANTHROPIC_BASE_URL") or "https://api.anthropic.com",
        ai_provider=(get("FINZORIA_AI_PROVIDER") or "anthropic").lower(),
        gemini_api_key=get("FINZORIA_GEMINI_API_KEY"),
        gemini_model=get("FINZORIA_GEMINI_MODEL"),
        ai_requests_per_minute=_int(get("FINZORIA_AI_REQUESTS_PER_MINUTE")),
        ai_requests_per_day=_int(get("FINZORIA_AI_REQUESTS_PER_DAY")),
        ai_requests_per_turn=_int(get("FINZORIA_AI_REQUESTS_PER_TURN")),
    )
