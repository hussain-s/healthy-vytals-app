"""Typed application/domain exceptions — pure, framework-free.

These describe *what went wrong in business terms* (not-found, conflict, illegal
state transition, …) and carry a stable machine-readable ``code`` plus the HTTP
status they should map to. They deliberately import **nothing** from FastAPI or
SQLAlchemy, so the domain layer can raise them while staying pure (DESIGN §7.6,
rule 3). ``core/errors.py`` translates them into HTTP responses; it re-exports
these names for backwards compatibility, so callers may import from either place.

HTTP status codes are plain integers here (not ``fastapi.status``) precisely to
keep this module dependency-free.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all domain/application errors.

    Subclasses set :attr:`code` (stable, machine-readable) and :attr:`http_status`.
    ``message`` is client-safe; ``details`` may carry structured, non-sensitive
    context. Business code raises these; it never constructs HTTP responses.
    """

    code: str = "error"
    http_status: int = 400

    def __init__(
        self, message: str | None = None, details: dict[str, object] | None = None
    ) -> None:
        self.message = message or self.__class__.__name__
        self.details = details
        super().__init__(self.message)


class NotFound(AppError):
    """A requested resource does not exist (or is not visible to the caller)."""

    code = "not_found"
    http_status = 404


class ValidationError(AppError):
    """Input is well-formed but violates a business validation rule."""

    code = "validation_error"
    http_status = 422


class AuthenticationError(AppError):
    """The caller is not authenticated (missing/invalid/expired credentials)."""

    code = "authentication_error"
    http_status = 401


class PermissionDenied(AppError):
    """The caller is authenticated but not allowed to perform this action."""

    code = "permission_denied"
    http_status = 403


class Conflict(AppError):
    """The request conflicts with current state (base for 409s)."""

    code = "conflict"
    http_status = 409


class IllegalTransition(Conflict):
    """A domain state machine was asked to make an illegal transition (§5.1).

    A 409 because it is a conflict with the entity's current state, not malformed
    input. Raised by the appointment state machine and mapped to HTTP by the
    handlers in ``core/errors.py``.
    """

    code = "illegal_transition"
