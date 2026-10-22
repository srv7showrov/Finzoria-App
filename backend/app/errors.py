"""Domain errors carry a stable code and a user-safe message."""

from __future__ import annotations


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def not_found(what: str) -> DomainError:
    # The same answer for "missing" and "belongs to another workspace".
    return DomainError(404, "not_found", f"{what} not found.")
