"""Finzoria FastAPI application."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import repositories as repo
from .ai import usage
from .ai.adapter import build_adapter, connection_status
from .clock import Clock
from .config import Settings, load_settings
from .db import Database
from .deps import SESSION_COOKIE, Workspace
from .errors import DomainError, not_found
from .money import MoneyError
from .routes import assistant, finance, payments, supporting
from .services import ledger, workspace_data
from .schemas import DeleteConfirm, PreferencesUpdate, ProfileUpdate, ResetConfirm

__all__ = ["SESSION_COOKIE", "create_app", "app"]

APP_VERSION = "0.4.0-stage-d"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

logger = logging.getLogger("finzoria")


def _error(status: int, code: str, message: str, **extra: object) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


def _origin_of(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.database_path)
    adapter = build_adapter(settings)
    allowed_origins = {o.lower() for o in settings.allowed_origins}

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        db.migrate()
        with db.transaction() as conn:
            repo.delete_expired_sessions(conn)
        yield

    app = FastAPI(title="Finzoria", version=APP_VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.db = db
    app.state.ai = adapter
    app.state.clock = Clock()

    # --- safety middleware and error handling --------------------------------

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Reject state-changing API requests that do not come from an allowed origin.

        No permissive CORS is configured; this blocks cross-site form/fetch posts that
        would otherwise ride on the session cookie.
        """
        if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/"):
            origin = _origin_of(request.headers.get("origin")) or _origin_of(request.headers.get("referer"))
            own = f"{request.url.scheme}://{request.headers.get('host', '')}".lower()
            if origin is None or (origin not in allowed_origins and origin != own):
                return _error(403, "origin_rejected", "Request origin is not allowed.")
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return _error(exc.status_code, str(exc.detail["code"]), str(exc.detail["message"]))
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, **exc.details)

    @app.exception_handler(MoneyError)
    async def money_error(_: Request, exc: MoneyError) -> JSONResponse:
        return _error(422, "invalid_amount", str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Report field locations and messages only; never echo submitted values.
        fields = [
            {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _error(422, "validation_error", "Some fields need attention.", fields=fields)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error: %s", type(exc).__name__)
        return _error(500, "internal_error", "Something went wrong. Please try again.")

    # --- routes -----------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, object]:
        with db.read() as conn:
            version = db.schema_version(conn)
            latest = repo.latest_ai_check(conn)
        return {
            "status": "ok",
            "version": APP_VERSION,
            "database": {"status": "ok", "schema_version": version},
            "ai": connection_status(app.state.ai, latest),
        }

    def _set_session_cookie(request: Request, response: Response, token: str) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=settings.session_days * 86400,
            httponly=True,
            samesite="lax",
            secure=settings.cookie_secure or request.url.scheme == "https",
            path="/",
        )

    @app.post("/api/session")
    def start_session(request: Request, response: Response) -> dict[str, object]:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            with db.read() as conn:
                existing = repo.workspace_for_token(conn, token)
            if existing:
                return {"workspace_id": existing, "created": False}
        with db.transaction() as conn:
            workspace_id, token = repo.create_workspace(conn, settings.session_days, app.state.clock)
        _set_session_cookie(request, response, token)
        return {"workspace_id": workspace_id, "created": True}

    # --- workspace data controls (only the session's own workspace) ----------------

    @app.get("/api/workspace/export")
    def export_workspace(workspace_id: Workspace) -> Response:
        with db.read() as conn:
            data = workspace_data.export(conn, workspace_id, app.state.clock.now())
        return Response(
            content=json.dumps(data, ensure_ascii=False, indent=2),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="finzoria-workspace-export.json"',
                     "X-Content-Type-Options": "nosniff"},
        )

    @app.post("/api/workspace/reset")
    def reset_workspace(body: ResetConfirm, request: Request, response: Response, workspace_id: Workspace) -> dict[str, object]:
        """Replaces the workspace with a fresh demo workspace, keeping language, currency and time zone."""
        with db.transaction() as conn:
            prefs = repo.get_preferences(conn, workspace_id)
            workspace_data.delete_workspace(conn, workspace_id)
            new_id, token = repo.create_workspace(conn, settings.session_days, app.state.clock)
            repo.update_preferences(conn, new_id, prefs["language"], prefs["display_currency"], prefs["time_zone"])
        _set_session_cookie(request, response, token)
        return {"reset": True}

    @app.post("/api/workspace/delete")
    def delete_workspace(body: DeleteConfirm, response: Response, workspace_id: Workspace) -> dict[str, object]:
        with db.transaction() as conn:
            workspace_data.delete_workspace(conn, workspace_id)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"deleted": True}

    @app.get("/api/session")
    def get_session(workspace_id: Workspace) -> dict[str, object]:
        return {"workspace_id": workspace_id, "data_mode": "demo"}

    @app.get("/api/profile")
    def get_profile(workspace_id: Workspace) -> dict[str, str]:
        with db.read() as conn:
            return repo.get_profile(conn, workspace_id)

    @app.put("/api/profile")
    def put_profile(body: ProfileUpdate, workspace_id: Workspace) -> dict[str, str]:
        with db.transaction() as conn:
            repo.update_profile(conn, workspace_id, body.display_name, body.institution)
            return repo.get_profile(conn, workspace_id)

    @app.get("/api/preferences")
    def get_preferences(workspace_id: Workspace) -> dict[str, str]:
        with db.read() as conn:
            return repo.get_preferences(conn, workspace_id)

    @app.put("/api/preferences")
    def put_preferences(body: PreferencesUpdate, workspace_id: Workspace) -> dict[str, str]:
        with db.transaction() as conn:
            repo.update_preferences(conn, workspace_id, body.language, body.display_currency, body.time_zone)
            return repo.get_preferences(conn, workspace_id)

    @app.get("/api/accounts")
    def get_accounts(workspace_id: Workspace) -> dict[str, object]:
        with db.read() as conn:
            return {"accounts": ledger.balances(conn, workspace_id)}

    @app.get("/api/accounts/{account_id}")
    def get_account(account_id: str, workspace_id: Workspace) -> dict[str, str]:
        with db.read() as conn:
            account = repo.get_account(conn, workspace_id, account_id)
        if account is None:
            # Same answer for "missing" and "belongs to another workspace".
            raise not_found("Account")
        return account

    @app.get("/api/ai/status")
    def ai_status() -> dict[str, object]:
        with db.read() as conn:
            status = connection_status(app.state.ai, repo.latest_ai_check(conn))
        return {**status, "requests": usage.summary(db, app.state.ai)}

    app.include_router(finance.router)
    app.include_router(payments.router)
    app.include_router(assistant.router)
    app.include_router(supporting.router)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(path: str) -> JSONResponse:
        return _error(404, "not_found", "Unknown API route.")

    # --- built frontend (local release path) -------------------------------------

    dist = settings.frontend_dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> Response:
        index = dist / "index.html"
        if not index.is_file():
            return _error(
                404, "frontend_not_built", "Frontend is not built. Run the build step or use the Vite dev server."
            )
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(index)

    return app


app = create_app()
