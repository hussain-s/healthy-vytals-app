"""Care-team messaging scope (v2 M9) — who may exchange messages with whom.

Messaging in HealthyVytals is deliberately *not* open: a patient converses only
with clinical staff on their care team, and a staff member converses only with
patients they are authorized to treat. This mirrors the treating-relationship
scoping used for history and labs (§5.3) rather than inventing a second rule.

This predicate is pure: it takes plain facts (the staff member's role and whether
a treating relationship exists) and returns a decision. The service supplies the
relationship fact from a repository; the predicate never touches the DB. That
keeps the rule unit-testable and documented, consistent with the other domain
rules (``access_scope``, ``lab_rules``, …).
"""

from __future__ import annotations

from app.core.roles import Role


def can_staff_message_patient(
    staff_role: Role,
    has_treating_relationship: bool,
) -> bool:
    """Return whether a staff member may share a message thread with a patient.

    Rules (mirroring §5.3 history scoping):
      * **Doctor** — only with a treating relationship (a shared
        appointment/encounter with that patient).
      * **Nurse** — clinical staff supporting care; may message patients.
      * **Admin** — operations/least-privilege: **no** clinical messaging; admins
        manage accounts, they are not part of a care conversation.
      * **Patient** — not "staff"; a patient is never the staff side of a thread.

    ``has_treating_relationship`` is only consulted for doctors; callers may pass
    ``False`` for other roles.
    """
    if staff_role is Role.DOCTOR:
        return has_treating_relationship
    if staff_role is Role.NURSE:
        return True
    # Admin and patient are never the authorized staff side of a care thread.
    return False
