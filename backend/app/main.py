"""Application factory and ASGI entrypoint.

:func:`create_app` builds and configures the FastAPI application: it mounts the
versioned JSON API and (in later slices) the server-rendered web UI, wires
middleware, and registers exception handlers. Using a factory — rather than a
module-level ``app`` built at import time — keeps construction explicit and lets
tests build isolated app instances.

The module also exposes a ready-built ``app`` for Uvicorn (``uvicorn
app.main:app``), which the dev scripts use to run the single process on ``:8000``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.web.appointments import router as web_appointments_router
from app.web.auth import router as web_auth_router
from app.web.clinical import router as web_clinical_router
from app.web.deps import _RedirectToLogin, _handle_login_redirect
from app.web.router import router as web_router

# Location of the web layer's static assets (app.css, vendored htmx.min.js).
_WEB_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

# API surface metadata shown at /docs (interactive OpenAPI).
_API_TITLE = "HealthyVytals API"
_API_DESCRIPTION = (
    "Local-first medical portal. JSON API for accounts, appointments, clinical "
    "records, and prescriptions. The browser UI is server-rendered (Jinja2 + HTMX) "
    "by this same application."
)
_API_VERSION = "0.1.0"


def create_app() -> FastAPI:
    """Build and return a configured FastAPI application instance."""
    settings = get_settings()

    app = FastAPI(
        title=_API_TITLE,
        description=_API_DESCRIPTION,
        version=_API_VERSION,
        # Hide interactive docs in production; they are a development convenience.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
    )

    # Map typed domain/application errors to stable HTTP responses.
    register_exception_handlers(app)
    # Protected web pages raise _RedirectToLogin → 303 to the login page.
    app.add_exception_handler(_RedirectToLogin, _handle_login_redirect)  # type: ignore[arg-type]

    # JSON API, versioned under /api/v1 (health, and later: auth, users, ...).
    app.include_router(api_router, prefix="/api")

    # Server-rendered web UI (Jinja2 + HTMX). Static assets are mounted with the
    # name "web-static" so templates can build asset URLs via url_for(...).
    app.mount(
        "/static",
        StaticFiles(directory=str(_WEB_STATIC_DIR)),
        name="web-static",
    )
    app.include_router(web_auth_router)
    app.include_router(web_appointments_router)
    app.include_router(web_clinical_router)
    app.include_router(web_router)

    # NOTE: audit middleware is wired in a later Phase 1 slice.

    return app


# ASGI application object for Uvicorn.
app = create_app()
