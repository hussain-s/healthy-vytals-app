"""Audit service — the single choke point for writing the audit trail (§5.7).

Every audited action goes through :func:`record_audit`, which appends one
immutable :class:`~app.models.audit.AuditLog` row. Centralizing writes here (a)
guarantees a consistent shape for every entry and (b) gives us one place to
evolve the policy later (e.g. add request context).

Transactional contract: the caller passes its ``Session``, so the audit row is
written **inside the same unit of work** as the action being audited. That means
the action and its audit record commit together or roll back together — you can
never have a booked appointment with no audit trail, or an audit row for an
action that was rolled back.

Action names use a dotted ``resource.verb`` convention (e.g. ``auth.login``,
``auth.login_failed``, ``user.register``) so the log is greppable and filterable.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def record_audit(
    session: Session,
    *,
    action: str,
    actor_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    patient_id: int | None = None,
    commit: bool = False,
) -> AuditLog:
    """Append an audit-log entry within the caller's transaction.

    Parameters are keyword-only (except the session) so call sites are
    self-documenting and cannot accidentally transpose ids. ``resource_id`` is
    accepted as int or str and stored as text, so it works for any id shape.

    By default the entry is flushed but **not** committed, so it is atomic with
    the audited action (they commit or roll back together) — the right behavior
    for a *successful* action.

    Set ``commit=True`` to persist the entry immediately, independent of the
    caller's transaction outcome. This is required when auditing a **failed**
    action that will raise afterward: the request's unit of work rolls back on
    that exception, which would otherwise discard the audit row. Only use it when
    the audit row is the sole pending write (e.g. a failed login), so committing
    cannot accidentally persist unrelated half-done work.
    """
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        patient_id=patient_id,
    )
    session.add(entry)
    if commit:
        session.commit()
    else:
        session.flush()
    return entry
