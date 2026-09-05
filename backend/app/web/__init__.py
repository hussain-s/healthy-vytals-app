"""Presentation layer — server-rendered Jinja2 + HTMX (DESIGN §7.3).

The browser UI is rendered by this same FastAPI app; there is no React/Node/build
step. Routes here are thin: they call the *same services* the JSON API calls and
render a template with the result. They hold no business logic and never touch
repositories or the database directly (DESIGN §7.6, rule 7). Reusable HTMX
fragments live under ``templates/partials/``.
"""
