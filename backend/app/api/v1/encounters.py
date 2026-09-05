"""Clinical API endpoints (JSON): encounters, vitals, diagnoses, addenda, history.

Thin controllers over clinical_service, role-gated by dependencies. Fine-grained
checks (encounter ownership, treating-relationship for history) live in the
service; routers only enforce the coarse role gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.roles import Role
from app.db.session import get_session
from app.domain.vitals_ranges import VitalsReading
from app.models.user import User
from app.schemas.encounter import (
    AddendumCreate,
    AddendumOut,
    DiagnosisCreate,
    DiagnosisOut,
    EncounterOpen,
    EncounterOut,
    VitalsAssessmentOut,
    VitalsCreate,
    VitalsOut,
)
from app.services import clinical_service, vitals_assistant_service

router = APIRouter(prefix="/encounters", tags=["clinical"])


@router.post("", response_model=EncounterOut, status_code=status.HTTP_201_CREATED,
             summary="Open an encounter (doctor only)")
def open_encounter(
    payload: EncounterOpen,
    doctor: User = Depends(require_roles(Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> EncounterOut:
    encounter = clinical_service.open_encounter(session, doctor.id, payload.appointment_id)
    return EncounterOut.model_validate(encounter)


@router.post("/{encounter_id}/vitals", response_model=VitalsOut,
             status_code=status.HTTP_201_CREATED, summary="Record vitals (nurse only)")
def record_vitals(
    encounter_id: int,
    payload: VitalsCreate,
    nurse: User = Depends(require_roles(Role.NURSE)),
    session: Session = Depends(get_session),
) -> VitalsOut:
    reading = VitalsReading(
        heart_rate=payload.heart_rate,
        resp_rate=payload.resp_rate,
        systolic_bp=payload.systolic_bp,
        temp_c=payload.temp_c,
        spo2=payload.spo2,
    )
    vitals = clinical_service.record_vitals(session, nurse.id, encounter_id, reading)
    return VitalsOut.model_validate(vitals)


@router.post(
    "/{encounter_id}/vitals-assessment",
    response_model=VitalsAssessmentOut,
    summary="AI-assisted vitals triage read (nurse or treating doctor)",
)
def assess_vitals(
    encounter_id: int,
    staff: User = Depends(require_roles(Role.NURSE, Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> VitalsAssessmentOut:
    """Return a structured, advisory AI assessment of the encounter's latest vitals.

    Decision-support, not diagnosis (§14, Rule #11): the deterministic age-based
    rule remains the source of truth and the model only explains its flags. Uses
    the configured LLM provider — the offline stub by default, or a real model when
    ``HV_LLM_PROVIDER`` + ``HV_LLM_API_KEY`` are set. Fine-grained authorization
    (a doctor's treating relationship) is enforced in the service.
    """
    assessment = vitals_assistant_service.assess_encounter_vitals(
        session, staff=staff, encounter_id=encounter_id
    )
    return VitalsAssessmentOut(
        summary=assessment.summary,
        urgency=assessment.urgency.value,
        red_flags=assessment.red_flags,
        recommended_action=assessment.recommended_action,
        confidence=assessment.confidence,
    )


@router.post("/{encounter_id}/diagnoses", response_model=DiagnosisOut,
             status_code=status.HTTP_201_CREATED, summary="Add a diagnosis (doctor only)")
def add_diagnosis(
    encounter_id: int,
    payload: DiagnosisCreate,
    doctor: User = Depends(require_roles(Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> DiagnosisOut:
    diagnosis = clinical_service.add_diagnosis(
        session, doctor.id, encounter_id, payload.icd_code, payload.description
    )
    return DiagnosisOut.model_validate(diagnosis)


@router.post("/addenda", response_model=AddendumOut, status_code=status.HTTP_201_CREATED,
             summary="Add a correction addendum (clinical staff)")
def add_addendum(
    payload: AddendumCreate,
    author: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AddendumOut:
    """Append an immutable correction. The service restricts this to clinical staff."""
    addendum = clinical_service.add_addendum(
        session, author.id, author.role, payload.target_type, payload.target_id, payload.note
    )
    return AddendumOut.model_validate(addendum)


@router.get("/history/{patient_id}", response_model=list[EncounterOut],
            summary="View a patient's encounter history (scoped)")
def patient_history(
    patient_id: int,
    viewer: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[EncounterOut]:
    """Return a patient's encounters, subject to treating-relationship scoping (§5.3)."""
    encounters = clinical_service.get_patient_history(
        session, viewer.id, viewer.role, patient_id
    )
    return [EncounterOut.model_validate(e) for e in encounters]
