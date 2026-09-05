"""Unit tests for the appointment state machine (app.domain.appointment_state).

Pure tests — no DB, no HTTP. They pin the legal transitions, the role gating, and
the terminal states from DESIGN §5.1, so any change to the rules is caught here.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import IllegalTransition
from app.core.roles import Role
from app.domain.appointment_state import (
    TERMINAL_STATES,
    AppointmentStatus,
    Transition,
    assert_transition_allowed,
    can_transition,
    target_state,
)


def test_happy_path_lifecycle() -> None:
    """requested → confirmed → checked_in → in_progress → completed, by role."""
    state = AppointmentStatus.REQUESTED
    state = assert_transition_allowed(state, Transition.CONFIRM, Role.DOCTOR)
    assert state is AppointmentStatus.CONFIRMED
    state = assert_transition_allowed(state, Transition.CHECK_IN, Role.NURSE)
    assert state is AppointmentStatus.CHECKED_IN
    state = assert_transition_allowed(state, Transition.BEGIN, Role.DOCTOR)
    assert state is AppointmentStatus.IN_PROGRESS
    state = assert_transition_allowed(state, Transition.COMPLETE, Role.DOCTOR)
    assert state is AppointmentStatus.COMPLETED


def test_illegal_transition_from_wrong_state_raises() -> None:
    """You cannot begin an appointment that has only been requested."""
    with pytest.raises(IllegalTransition) as exc:
        assert_transition_allowed(AppointmentStatus.REQUESTED, Transition.BEGIN, Role.DOCTOR)
    assert exc.value.code == "illegal_transition"
    assert exc.value.http_status == 409


def test_role_not_permitted_raises_even_if_state_is_legal() -> None:
    """A patient may not confirm (a doctor action), though the state allows confirm."""
    # State legality holds (confirm is valid from requested)...
    assert can_transition(AppointmentStatus.REQUESTED, Transition.CONFIRM, Role.DOCTOR) is True
    # ...but the patient role is rejected.
    with pytest.raises(IllegalTransition, match="may not 'confirm'"):
        assert_transition_allowed(AppointmentStatus.REQUESTED, Transition.CONFIRM, Role.PATIENT)


def test_patient_can_cancel_but_not_check_in() -> None:
    assert can_transition(AppointmentStatus.CONFIRMED, Transition.CANCEL, Role.PATIENT) is True
    assert can_transition(AppointmentStatus.CONFIRMED, Transition.CHECK_IN, Role.PATIENT) is False


def test_nurse_checks_in_and_marks_no_show() -> None:
    assert can_transition(AppointmentStatus.CONFIRMED, Transition.CHECK_IN, Role.NURSE) is True
    assert can_transition(AppointmentStatus.CHECKED_IN, Transition.NO_SHOW, Role.NURSE) is True


def test_reschedule_returns_to_requested() -> None:
    result = assert_transition_allowed(
        AppointmentStatus.CONFIRMED, Transition.RESCHEDULE, Role.PATIENT
    )
    assert result is AppointmentStatus.REQUESTED


def test_terminal_states_have_no_outgoing_transitions() -> None:
    for terminal in TERMINAL_STATES:
        for transition in Transition:
            for role in Role:
                assert can_transition(terminal, transition, role) is False


def test_cancel_not_allowed_once_in_progress() -> None:
    """An in-progress visit cannot be cancelled (only completed)."""
    with pytest.raises(IllegalTransition):
        assert_transition_allowed(AppointmentStatus.IN_PROGRESS, Transition.CANCEL, Role.PATIENT)


def test_target_state_is_independent_of_current() -> None:
    assert target_state(Transition.COMPLETE) is AppointmentStatus.COMPLETED
    assert target_state(Transition.CANCEL) is AppointmentStatus.CANCELLED
