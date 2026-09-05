"""Prescription API endpoints (JSON): prescribe (safety-checked) and view.

Thin controllers over prescription_service. The §5.4 safety logic and ownership
checks live in the service; the router only enforces the coarse role gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import Role
from app.db.session import get_session
from app.models.user import User
from app.schemas.prescription import PrescribeRequest, PrescriptionOut
from app.services import prescription_service

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@router.post("", response_model=PrescriptionOut, status_code=status.HTTP_201_CREATED,
             summary="Prescribe a medication (doctor only, safety-checked)")
def prescribe(
    payload: PrescribeRequest,
    doctor: User = Depends(require_roles(Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> PrescriptionOut:
    """Prescribe within an encounter after §5.4 safety checks (story D1).

    A safety block raises ``UnsafePrescription`` → 409 with a ``reason`` in the
    error details (allergy | interaction | refill_cap). An interaction can be
    proceeded past with ``override_interaction=true``; an allergy cannot.
    """
    rx = prescription_service.prescribe(
        session,
        doctor.id,
        payload.encounter_id,
        payload.medication_id,
        payload.dose,
        payload.refills,
        override_interaction=payload.override_interaction,
    )
    return PrescriptionOut.model_validate(rx)


@router.get("/mine", response_model=list[PrescriptionOut],
            summary="A patient's own prescriptions")
def my_prescriptions(
    patient: User = Depends(require_roles(Role.PATIENT)),
    session: Session = Depends(get_session),
) -> list[PrescriptionOut]:
    """Return the authenticated patient's prescriptions (story D5)."""
    rxs = prescription_service.list_for_patient(session, patient.id)
    return [PrescriptionOut.model_validate(r) for r in rxs]


@router.get("/patient/{patient_id}", response_model=list[PrescriptionOut],
            summary="A patient's prescriptions (clinical staff)")
def patient_prescriptions(
    patient_id: int,
    staff: User = Depends(require_roles(Role.DOCTOR, Role.NURSE)),
    session: Session = Depends(get_session),
) -> list[PrescriptionOut]:
    """Return a patient's prescriptions for treating staff (story D5)."""
    rxs = prescription_service.list_for_patient(session, patient_id)
    return [PrescriptionOut.model_validate(r) for r in rxs]
