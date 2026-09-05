"""Treating-relationship scoping (§5.3) — who may read a patient's history.

The access-control matrix (§6) says a doctor can read a patient's full history
*only if* they have a treating relationship — i.e. they have (or had) an
appointment/encounter with that patient. Role alone cannot express this: "is a
doctor" is necessary but not sufficient; "is THIS patient's doctor" is the real
question. That distinction is exactly why authorization is two-layered (coarse
role guard + fine service check), and this pure predicate is the fine check's
brain.

It is deliberately pure: it takes plain facts (the viewer's role and id, the
target patient id, and whether a treating relationship exists) and returns a
decision. The service layer supplies the relationship fact from a repository; the
predicate never touches the DB. This keeps the rule unit-testable and documented.
"""

from __future__ import annotations

from app.core.roles import Role


def can_view_patient_history(
    viewer_role: Role,
    viewer_id: int,
    patient_id: int,
    has_treating_relationship: bool,
) -> bool:
    """Return whether the viewer may read ``patient_id``'s full medical history.

    Rules (DESIGN §6, §5.3):
      * **Patient** — may read only their **own** history.
      * **Doctor** — may read a patient's history only with a treating
        relationship (an appointment/encounter with that patient).
      * **Nurse** — clinical staff supporting care; may read patient history
        (ward-scoped in a fuller model; v1 grants read to support triage).
      * **Admin** — operations/least-privilege: **no** clinical read access; admin
        manages accounts and reads the audit log, not PHI.

    ``has_treating_relationship`` is only consulted for doctors; callers may pass
    ``False`` for other roles.
    """
    if viewer_role is Role.PATIENT:
        return viewer_id == patient_id
    if viewer_role is Role.DOCTOR:
        return has_treating_relationship
    if viewer_role is Role.NURSE:
        return True
    # Admin (and any future non-clinical role) get no clinical read.
    return False


def is_encounter_visible(
    viewer_role: Role,
    viewer_id: int,
    patient_id: int,
    *,
    sensitive: bool,
    consent_shared: bool,
) -> bool:
    """Return whether a single encounter is visible to the viewer (consent gate, §5.8).

    Layered on top of :func:`can_view_patient_history`:
      * The patient always sees their **own** encounters (consent governs sharing
        with others, not self-access).
      * A **sensitive** encounter is hidden from otherwise-authorized staff unless
        the patient has granted consent to share it (``consent_shared``).
      * A non-sensitive encounter follows normal history-read rules.

    This does not itself check the treating relationship — callers apply
    :func:`can_view_patient_history` first to decide *access to the history at
    all*, then this per-record filter to honor consent on sensitive rows.
    """
    if viewer_role is Role.PATIENT and viewer_id == patient_id:
        return True
    if sensitive and not consent_shared:
        return False
    return True
