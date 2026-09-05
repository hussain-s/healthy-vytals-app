"""Unit tests for treating-relationship scoping (app.domain.access_scope), §5.3."""

from __future__ import annotations

from app.core.roles import Role
from app.domain.access_scope import can_view_patient_history, is_encounter_visible


def test_patient_can_view_own_only() -> None:
    assert can_view_patient_history(Role.PATIENT, 1, 1, False) is True
    assert can_view_patient_history(Role.PATIENT, 1, 2, False) is False


def test_doctor_needs_treating_relationship() -> None:
    assert can_view_patient_history(Role.DOCTOR, 5, 9, True) is True
    assert can_view_patient_history(Role.DOCTOR, 5, 9, False) is False


def test_nurse_may_read_history() -> None:
    assert can_view_patient_history(Role.NURSE, 3, 9, False) is True


def test_admin_has_no_clinical_read() -> None:
    """Separation of duties: admin manages accounts/audit, not PHI."""
    assert can_view_patient_history(Role.ADMIN, 7, 9, True) is False


# --- consent gating (§5.8) ---


def test_patient_sees_own_sensitive_encounter() -> None:
    assert is_encounter_visible(Role.PATIENT, 1, 1, sensitive=True, consent_shared=False) is True


def test_staff_hidden_from_sensitive_without_consent() -> None:
    assert is_encounter_visible(Role.DOCTOR, 5, 1, sensitive=True, consent_shared=False) is False
    assert is_encounter_visible(Role.NURSE, 3, 1, sensitive=True, consent_shared=False) is False


def test_staff_sees_sensitive_with_consent() -> None:
    assert is_encounter_visible(Role.DOCTOR, 5, 1, sensitive=True, consent_shared=True) is True


def test_non_sensitive_always_visible_to_staff() -> None:
    assert is_encounter_visible(Role.DOCTOR, 5, 1, sensitive=False, consent_shared=False) is True
