"""Lab API endpoints (JSON, v2 M8): order, record result, view.

Thin controllers over lab_service. Coarse role gates here; fine ownership /
treating-relationship checks live in the service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.roles import Role
from app.db.session import get_session
from app.models.user import User
from app.schemas.lab import (
    LabOrderCreate,
    LabOrderOut,
    LabResultCreate,
    LabResultOut,
)
from app.services import lab_service

router = APIRouter(prefix="/labs", tags=["labs"])


@router.post("/orders", response_model=LabOrderOut, status_code=status.HTTP_201_CREATED,
             summary="Order a lab on an encounter (doctor only)")
def order_lab(
    payload: LabOrderCreate,
    doctor: User = Depends(require_roles(Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> LabOrderOut:
    order = lab_service.order_lab(
        session, doctor.id, payload.encounter_id,
        payload.test_code, payload.test_name, payload.notes,
    )
    return LabOrderOut.model_validate(order)


@router.post("/orders/{lab_order_id}/results", response_model=LabResultOut,
             status_code=status.HTTP_201_CREATED,
             summary="Record a lab result (clinical staff)")
def record_result(
    lab_order_id: int,
    payload: LabResultCreate,
    staff: User = Depends(require_roles(Role.NURSE, Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> LabResultOut:
    result = lab_service.record_result(
        session, staff.id, staff.role, lab_order_id,
        payload.analyte, payload.value, payload.unit,
        payload.reference_low, payload.reference_high,
    )
    return LabResultOut.model_validate(result)


@router.get("/patient/{patient_id}", response_model=list[LabOrderOut],
            summary="A patient's lab orders (scoped)")
def patient_labs(
    patient_id: int,
    viewer: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[LabOrderOut]:
    """Return a patient's lab orders, subject to treating-relationship scoping (§5.3)."""
    rows = lab_service.get_patient_labs(session, viewer.id, viewer.role, patient_id)
    return [LabOrderOut.model_validate(r["order"]) for r in rows]
