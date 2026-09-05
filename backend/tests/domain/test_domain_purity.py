"""Guard test: the domain layer must stay pure (DESIGN §7.6, rule 3).

Domain modules encode business rules and must not import web/DB frameworks, so
they remain unit-testable in isolation. This test inspects the source of every
module under app/domain and fails if it imports fastapi or sqlalchemy — a
structural invariant that is easy to violate accidentally in a later slice.
"""

from __future__ import annotations

import pathlib

import app.domain as domain_pkg

_FORBIDDEN = ("fastapi", "sqlalchemy")


def test_domain_modules_do_not_import_frameworks() -> None:
    domain_dir = pathlib.Path(domain_pkg.__file__).parent
    offenders: list[str] = []
    for path in domain_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN:
            # Match import statements specifically, not the word in a comment.
            if f"import {token}" in source or f"from {token}" in source:
                offenders.append(f"{path.name} imports {token}")
    assert offenders == [], f"domain purity violated: {offenders}"
