"""Tests for the pure care-team messaging rule (app.domain.messaging_rules)."""

from __future__ import annotations

from app.core.roles import Role
from app.domain.messaging_rules import can_staff_message_patient


def test_doctor_needs_treating_relationship() -> None:
    assert can_staff_message_patient(Role.DOCTOR, True) is True
    assert can_staff_message_patient(Role.DOCTOR, False) is False


def test_nurse_may_always_message() -> None:
    assert can_staff_message_patient(Role.NURSE, False) is True


def test_admin_and_patient_are_never_staff_side() -> None:
    assert can_staff_message_patient(Role.ADMIN, True) is False
    assert can_staff_message_patient(Role.PATIENT, True) is False
