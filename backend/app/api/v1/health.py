"""Health-check endpoint.

A liveness/readiness probe that reports whether the app is up and whether it can
reach its database. Kept dependency-light and side-effect-free so it is safe to
poll frequently (scripts, load balancers, a developer checking the app booted).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.db.session import get_engine

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health report: overall status plus a database-connectivity flag."""

    status: str
    database: str


@router.get("/health", response_model=HealthResponse, summary="Liveness/readiness probe")
def health() -> HealthResponse:
    """Return ``ok`` when the app is serving, plus DB reachability.

    The database check runs a trivial ``SELECT 1``. A failure degrades the
    ``database`` field to ``"unavailable"`` rather than raising, so the probe
    still returns 200 and the caller can distinguish "app down" (no response)
    from "app up but DB unreachable" (``database != "ok"``).
    """
    database = "ok"
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    return HealthResponse(status="ok", database=database)
