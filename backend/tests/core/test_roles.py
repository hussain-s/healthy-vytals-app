"""Tests for roles and RBAC groupings (app.core.roles).

These pin the *design decisions* encoded in the groupings — e.g. that admin has
no clinical authoring rights and that only admin reads the audit log (DESIGN §6).
If a future change widened these sets, these tests would fail loudly.
"""

from __future__ import annotations

from app.core.roles import (
    AUDIT_READERS,
    CLINICAL_AUTHORS,
    CLINICAL_STAFF,
    STAFF,
    Role,
    has_role,
)


def test_role_serializes_as_its_string_value() -> None:
    """Role is a str-enum so it flows through JSON/JWT/DB as a plain string."""
    assert Role.DOCTOR == "doctor"
    assert Role.DOCTOR.value == "doctor"
    assert {r.value for r in Role} == {"patient", "nurse", "doctor", "admin"}


def test_clinical_staff_excludes_patient_and_admin() -> None:
    assert CLINICAL_STAFF == frozenset({Role.NURSE, Role.DOCTOR})
    assert Role.PATIENT not in CLINICAL_STAFF
    assert Role.ADMIN not in CLINICAL_STAFF


def test_staff_is_every_non_patient_role() -> None:
    assert STAFF == frozenset({Role.NURSE, Role.DOCTOR, Role.ADMIN})
    assert Role.PATIENT not in STAFF


def test_only_doctor_authors_clinical_records() -> None:
    """Least-privilege: nurses record vitals but do not author; admin never does."""
    assert CLINICAL_AUTHORS == frozenset({Role.DOCTOR})
    assert Role.NURSE not in CLINICAL_AUTHORS
    assert Role.ADMIN not in CLINICAL_AUTHORS


def test_only_admin_reads_audit_log() -> None:
    """Separation of duties: no clinical role may read the PHI-access audit log."""
    assert AUDIT_READERS == frozenset({Role.ADMIN})
    for role in (Role.PATIENT, Role.NURSE, Role.DOCTOR):
        assert role not in AUDIT_READERS


def test_has_role_membership_helper() -> None:
    assert has_role(Role.DOCTOR, CLINICAL_AUTHORS) is True
    assert has_role(Role.NURSE, CLINICAL_AUTHORS) is False
