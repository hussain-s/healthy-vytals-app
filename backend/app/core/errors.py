"""HTTP exception handlers that render the typed domain/application errors.

The semantic exception hierarchy (``AppError`` and friends) lives in
``app.core.exceptions`` so it stays framework-free and the domain layer can raise
it without importing FastAPI (DESIGN §7.6, rules 3 & 6). This module is the single
place that maps each exception to an HTTP status code and the standard
:class:`ErrorResponse` envelope, and it re-exports the exception types so existing
imports (``from app.core.errors import NotFound``) keep working.

Register the handlers on an app with :func:`register_exception_handlers`, called
from the app factory.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Re-export the pure exception hierarchy so callers may import from either module.
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    Conflict,
    IllegalTransition,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from app.schemas.common import ErrorResponse

__all__ = [
    "AppError",
    "AuthenticationError",
    "Conflict",
    "IllegalTransition",
    "NotFound",
    "PermissionDenied",
    "ValidationError",
    "register_exception_handlers",
]


# --- HTTP handlers ----------------------------------------------------------


def _error_json(status_code: int, payload: ErrorResponse) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    """Render any AppError as its declared status + the standard envelope."""
    return _error_json(
        exc.http_status,
        ErrorResponse(code=exc.code, message=exc.message, details=exc.details),
    )


async def _handle_request_validation(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map FastAPI/Pydantic request-validation failures onto ErrorResponse.

    Keeps the *same* envelope and a stable ``code`` for malformed input as for
    domain errors, so clients have one error contract. Pydantic's structured
    error list is passed through under ``details`` (field locations + messages),
    which is non-sensitive.
    """
    # exc.errors() can embed non-JSON-serializable objects (e.g. a ValueError in
    # a validator's ctx); jsonable_encoder coerces them to safe primitives.
    return _error_json(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        ErrorResponse(
            code="request_validation_error",
            message="Request validation failed.",
            details={"errors": jsonable_encoder(exc.errors())},
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register the app-wide exception handlers on ``app``.

    Registering the ``AppError`` base handler catches every subclass, so new
    semantic errors are rendered consistently without extra wiring.
    """
    app.add_exception_handler(AppError, _handle_app_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_request_validation)  # type: ignore[arg-type]
