"""User roles and coarse RBAC groupings.

This module is the authoritative definition of *who* exists in the system. It is
intentionally dependency-free (pure standard library) so it can be imported from
any layer — models, domain, services, api, web — without creating import cycles.

Two levels of access control build on this (see DESIGN §6):

    * **Coarse** (this module + route guards): "is the caller a clinician at all?"
      Expressed as role groupings like :data:`CLINICAL_STAFF`.
    * **Fine** (service layer): ownership and treating-relationship checks, e.g.
      "is this the doctor who actually treats this patient?" (§5.3). Those cannot
      be answered by role alone and therefore do not live here.

The groupings below encode design decisions that are *not* obvious from the code
that uses them, so each is documented with its rationale — this is exactly the
knowledge-base value the project exists to demonstrate.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """A user's role. Inherits from ``str`` so it serializes as its plain value
    (e.g. ``"patient"``) in JSON, tokens, and the database without extra mapping.
    """

    PATIENT = "patient"
    NURSE = "nurse"
    DOCTOR = "doctor"
    ADMIN = "admin"


# --- Coarse RBAC groupings (see DESIGN §2, §6) -----------------------------
# Frozensets: immutable (cannot be mutated at runtime by accident) and fast for
# membership tests in route guards.

#: Clinical staff who work inside the care workflow. Distinct from ADMIN, which
#: is an operations role with NO clinical authoring rights (least-privilege).
CLINICAL_STAFF: frozenset[Role] = frozenset({Role.NURSE, Role.DOCTOR})

#: Every non-patient account. Used where the distinction that matters is
#: "internal staff member" vs. "member of the public".
STAFF: frozenset[Role] = frozenset({Role.NURSE, Role.DOCTOR, Role.ADMIN})

#: Roles permitted to author immutable clinical records (diagnoses,
#: prescriptions). Only DOCTOR — nurses record vitals but do not diagnose or
#: prescribe, and admins never author clinical data (§6).
CLINICAL_AUTHORS: frozenset[Role] = frozenset({Role.DOCTOR})

#: Roles allowed to read the PHI-access audit log. Only ADMIN; granting this to
#: a clinical role would break the separation-of-duties the audit trail exists
#: to guarantee (§6, §5.7).
AUDIT_READERS: frozenset[Role] = frozenset({Role.ADMIN})


def has_role(role: Role, allowed: frozenset[Role]) -> bool:
    """Return whether ``role`` is a member of the ``allowed`` grouping.

    A tiny, explicitly-named helper so call sites in route guards read as intent
    (``has_role(user.role, CLINICAL_AUTHORS)``) rather than raw set operations.
    """
    return role in allowed
