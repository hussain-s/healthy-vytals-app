"""Jinja2 templating setup for the web layer.

Exposes a single configured :class:`~fastapi.templating.Jinja2Templates` instance
(:data:`templates`) that web routes use to render HTML. Centralizing the
configuration here means every route renders with the same environment (template
search path, autoescaping) and there is one place to add global template context
or filters later.

Autoescaping is on by default in Jinja2's ``select_autoescape`` for ``.html``
files, which is the key XSS defense for server-rendered pages: any value
interpolated into markup is HTML-escaped unless explicitly marked safe.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

# Templates live alongside this module in ./templates. Resolve from __file__ so
# the path is correct regardless of the process's working directory.
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
