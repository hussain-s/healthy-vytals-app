"""Top-level API router — aggregates every versioned sub-router.

``main.py`` includes this single router under the ``/api`` prefix, and each API
version nests beneath it (``/api/v1/...``). Adding a new resource means writing a
router in ``v1/`` and wiring it here; introducing ``v2`` later means adding a
second block without disturbing ``v1``. This is how the API stays versioned from
day one (DESIGN §7.6, rule 5).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    appointments,
    auth,
    encounters,
    health,
    labs,
    messages,
    prescriptions,
    users,
)

api_router = APIRouter()

# --- v1 ---
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(health.router)
v1_router.include_router(auth.router)
v1_router.include_router(users.router)
v1_router.include_router(appointments.router)
v1_router.include_router(encounters.router)
v1_router.include_router(prescriptions.router)
v1_router.include_router(labs.router)
v1_router.include_router(messages.router)

api_router.include_router(v1_router)
