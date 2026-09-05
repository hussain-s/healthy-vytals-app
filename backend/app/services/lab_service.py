"""Lab service — order labs, record results, and view them (scoped + audited).

Orchestrates the M8 use cases (DESIGN §13.2) inside the caller's unit of work:

    * doctor **orders** a lab on their encounter;
    * a nurse/lab **records** a result value (flagged abnormal by the pure rule),
      which also advances the order to ``resulted``;
    * patient / treating doctor / nurse **view** a patient's lab orders + results,
      reusing the treating-relationship scoping (§5.3) already used for history.

Every action is audited (§5.7). Results are append-only (§5.6): recording adds
rows and never edits prior ones.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, PermissionDenied
from app.core.roles import Role
from app.domain.access_scope import can_view_patient_history
from app.domain.lab_rules import is_abnormal
from app.models.lab import LabOrder, LabResult
from app.repositories.encounter_repository import EncounterRepository
from app.repositories.lab_repository import LabOrderRepository, LabResultRepository
from app.services import notification_service
from app.services.audit_service import record_audit


def order_lab(
    session: Session,
    doctor_id: int,
    encounter_id: int,
    test_code: str,
    test_name: str,
    notes: str | None = None,
) -> LabOrder:
    """Place a lab order on an encounter (doctor only; must own the encounter)."""
    encounter = EncounterRepository(session).get(encounter_id)
    if encounter is None:
        raise NotFound(f"No such encounter: {encounter_id}")
    if encounter.doctor_id != doctor_id:
        raise PermissionDenied("Only the encounter's doctor may order labs")

    order = LabOrderRepository(session).add(
        LabOrder(
            encounter_id=encounter_id,
            patient_id=encounter.patient_id,
            ordered_by=doctor_id,
            test_code=test_code,
            test_name=test_name,
            notes=notes,
        )
    )
    record_audit(
        session,
        action="lab.order",
        actor_id=doctor_id,
        resource_type="lab_order",
        resource_id=order.id,
        patient_id=encounter.patient_id,
    )
    return order


def record_result(
    session: Session,
    recorder_id: int,
    recorder_role: Role,
    lab_order_id: int,
    analyte: str,
    value: float,
    unit: str | None = None,
    reference_low: float | None = None,
    reference_high: float | None = None,
) -> LabResult:
    """Record a result value against an order (nurse/doctor); flags abnormal (M8).

    Clinical staff only. Computes ``abnormal`` from the pure lab rule, appends the
    result, marks the order ``resulted``, and audits. Append-only — never edits a
    prior result.
    """
    if recorder_role not in (Role.NURSE, Role.DOCTOR):
        raise PermissionDenied("Only clinical staff may record lab results")

    orders = LabOrderRepository(session)
    order = orders.get(lab_order_id)
    if order is None:
        raise NotFound(f"No such lab order: {lab_order_id}")

    abnormal = is_abnormal(value, reference_low, reference_high)
    result = LabResultRepository(session).add(
        LabResult(
            lab_order_id=lab_order_id,
            recorded_by=recorder_id,
            analyte=analyte,
            value=value,
            unit=unit,
            reference_low=reference_low,
            reference_high=reference_high,
            abnormal=abnormal,
        )
    )
    order.status = "resulted"
    session.flush()
    record_audit(
        session,
        action="lab.result",
        actor_id=recorder_id,
        resource_type="lab_result",
        resource_id=result.id,
        patient_id=order.patient_id,
    )
    # Let the patient know a result is available (in-app feed, M9).
    notification_service.notify(
        session,
        user_id=order.patient_id,
        event_type="lab.resulted",
        message=f"A new lab result was recorded ({analyte}).",
        link="/clinical/labs",
    )
    return result


def get_patient_labs(
    session: Session, viewer_id: int, viewer_role: Role, patient_id: int
) -> list[dict]:
    """Return a patient's lab orders (each with its results), if the viewer may.

    Reuses the treating-relationship scoping (§5.3): a doctor needs a treating
    relationship, a patient sees only their own, a nurse may read, admin may not.
    A denied read is audited (lab.read_denied, committed) and raises 403; an
    allowed read is audited (lab.read).
    """
    treating = (
        EncounterRepository(session).has_treating_relationship(viewer_id, patient_id)
        if viewer_role is Role.DOCTOR
        else False
    )
    if not can_view_patient_history(viewer_role, viewer_id, patient_id, treating):
        record_audit(
            session,
            action="lab.read_denied",
            actor_id=viewer_id,
            resource_type="lab_order",
            patient_id=patient_id,
            commit=True,
        )
        raise PermissionDenied("You may not view this patient's labs")

    record_audit(
        session,
        action="lab.read",
        actor_id=viewer_id,
        resource_type="lab_order",
        patient_id=patient_id,
    )
    orders = LabOrderRepository(session)
    results = LabResultRepository(session)
    return [
        {"order": o, "results": results.list_for_order(o.id)}
        for o in orders.list_for_patient(patient_id)
    ]
