"""Appointment state machine — legal transitions and who may trigger them (§5.1).

This is pure domain logic: it knows the *rules* of how an appointment may move
between states and which role is allowed to drive each move, but nothing about
the database, HTTP, or how an appointment is stored. Services call
:func:`assert_transition_allowed` (or :func:`can_transition`) before persisting a
status change.

The lifecycle (DESIGN §5.1):

    requested ──confirm──▶ confirmed ──check_in──▶ checked_in ──begin──▶
        in_progress ──complete──▶ completed

    side branches:
        requested / confirmed / checked_in ──cancel──▶ cancelled
        checked_in ──no_show──▶ no_show
        confirmed / checked_in ──reschedule──▶ requested

Who may trigger each transition encodes the access rules an AI can't guess:
    * a **patient** may cancel or reschedule their own appointment;
    * a **nurse** checks patients in and marks no-shows;
    * a **doctor** confirms, begins, and completes the clinical visit.
Terminal states (completed, cancelled, no_show) have no outgoing transitions.
"""

from __future__ import annotations

from enum import Enum

from app.core.exceptions import IllegalTransition
from app.core.roles import Role


class AppointmentStatus(str, Enum):
    """The states an appointment can occupy. Stored as its string value."""

    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Transition(str, Enum):
    """The named actions that move an appointment between states."""

    CONFIRM = "confirm"
    CHECK_IN = "check_in"
    BEGIN = "begin"
    COMPLETE = "complete"
    CANCEL = "cancel"
    NO_SHOW = "no_show"
    RESCHEDULE = "reschedule"


# Each transition: the states it may be applied from, the resulting state, and
# the roles permitted to trigger it. This table IS the rule — everything else
# reads from it, so there is one authoritative source (mirrors DESIGN §5.1 / §6).
_TRANSITIONS: dict[Transition, tuple[frozenset[AppointmentStatus], AppointmentStatus, frozenset[Role]]] = {
    Transition.CONFIRM: (
        frozenset({AppointmentStatus.REQUESTED}),
        AppointmentStatus.CONFIRMED,
        frozenset({Role.DOCTOR}),
    ),
    Transition.CHECK_IN: (
        frozenset({AppointmentStatus.CONFIRMED}),
        AppointmentStatus.CHECKED_IN,
        frozenset({Role.NURSE}),
    ),
    Transition.BEGIN: (
        frozenset({AppointmentStatus.CHECKED_IN}),
        AppointmentStatus.IN_PROGRESS,
        frozenset({Role.DOCTOR}),
    ),
    Transition.COMPLETE: (
        frozenset({AppointmentStatus.IN_PROGRESS}),
        AppointmentStatus.COMPLETED,
        frozenset({Role.DOCTOR}),
    ),
    Transition.CANCEL: (
        frozenset(
            {
                AppointmentStatus.REQUESTED,
                AppointmentStatus.CONFIRMED,
                AppointmentStatus.CHECKED_IN,
            }
        ),
        AppointmentStatus.CANCELLED,
        # Patients cancel their own; staff can cancel on the clinic's behalf.
        frozenset({Role.PATIENT, Role.NURSE, Role.DOCTOR}),
    ),
    Transition.NO_SHOW: (
        frozenset({AppointmentStatus.CHECKED_IN, AppointmentStatus.CONFIRMED}),
        AppointmentStatus.NO_SHOW,
        frozenset({Role.NURSE, Role.DOCTOR}),
    ),
    Transition.RESCHEDULE: (
        frozenset({AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN}),
        AppointmentStatus.REQUESTED,
        frozenset({Role.PATIENT, Role.DOCTOR}),
    ),
}

# States from which no transition is possible — the end of a lifecycle.
TERMINAL_STATES: frozenset[AppointmentStatus] = frozenset(
    {AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW}
)


def target_state(transition: Transition) -> AppointmentStatus:
    """Return the state a transition leads to (independent of the current state)."""
    return _TRANSITIONS[transition][1]


def can_transition(
    current: AppointmentStatus, transition: Transition, role: Role
) -> bool:
    """Return whether ``role`` may apply ``transition`` from the ``current`` state.

    Pure predicate — no exceptions, no I/O. Both the legality of the state change
    and the role permission must hold.
    """
    allowed_from, _, allowed_roles = _TRANSITIONS[transition]
    return current in allowed_from and role in allowed_roles


def assert_transition_allowed(
    current: AppointmentStatus, transition: Transition, role: Role
) -> AppointmentStatus:
    """Validate a transition and return the resulting state, or raise.

    Raises :class:`IllegalTransition` (409) with a specific message when the
    transition is not legal from ``current`` (or from a terminal state), and when
    the state change would be legal but the ``role`` is not permitted to trigger
    it. Distinguishing these two cases keeps the error messages honest and useful.
    """
    allowed_from, result, allowed_roles = _TRANSITIONS[transition]

    if current not in allowed_from:
        raise IllegalTransition(
            f"Cannot '{transition.value}' an appointment in state '{current.value}'",
            details={"current": current.value, "transition": transition.value},
        )
    if role not in allowed_roles:
        raise IllegalTransition(
            f"Role '{role.value}' may not '{transition.value}' an appointment",
            details={"role": role.value, "transition": transition.value},
        )
    return result
