"""Request dependencies: session → workspace, and per-request workspace context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from . import repositories as repo
from .clock import Clock
from .db import Database

SESSION_COOKIE = "finzoria_session"


def current_workspace(request: Request) -> str:
    """Resolve the demo workspace from the opaque HttpOnly session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db: Database = request.app.state.db
        with db.read() as conn:
            workspace_id = repo.workspace_for_token(conn, token)
        if workspace_id:
            return workspace_id
    raise HTTPException(401, {"code": "no_session", "message": "Start a demo workspace first."})


Workspace = Annotated[str, Depends(current_workspace)]


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: str
    db: Database
    clock: Clock
    time_zone: str
    display_currency: str
    language: str = "en"

    def now(self) -> datetime:
        return self.clock.now()

    def today(self) -> date:
        return self.clock.today(self.time_zone)


def workspace_context(request: Request, workspace_id: Workspace) -> WorkspaceContext:
    db: Database = request.app.state.db
    with db.read() as conn:
        prefs = repo.get_preferences(conn, workspace_id)
    return WorkspaceContext(workspace_id, db, request.app.state.clock, prefs["time_zone"], prefs["display_currency"],
                            prefs["language"])


Ctx = Annotated[WorkspaceContext, Depends(workspace_context)]
