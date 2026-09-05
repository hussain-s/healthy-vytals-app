"""Web (HTML/HTMX) clinical screens: patient history and doctor encounter actions.

Thin presentation over clinical_service (DESIGN §7.6, rule 7). Scoping and
immutability live in the service; these routes render what the caller is allowed
to see. v1 scope: a patient's own history view, and a doctor's encounter page
(record a diagnosis via HTMX). Vitals entry for nurses reuses the same pattern.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.roles import Role
from app.db.session import get_session
from app.models.user import User
from app.repositories.encounter_repository import EncounterRepository
from app.repositories.prescription_repository import (
    MedicationRepository,
    PrescriptionRepository,
)
from app.services import clinical_service, prescription_service
from app.web.deps import require_web_user
from app.web.templates import templates

router = APIRouter(prefix="/clinical", include_in_schema=False)


@router.get("/history", response_class=HTMLResponse, name="web-my-history")
def my_history(
    request: Request,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """A patient's own medical history (encounters), scoped by the service."""
    encounters = clinical_service.get_patient_history(session, user.id, user.role, user.id)
    # Attach each encounter's diagnoses for display.
    repo = EncounterRepository(session)
    rows = [
        {"encounter": e, "diagnoses": repo.diagnoses_for_encounter(e.id), "vitals": repo.vitals_for_encounter(e.id)}
        for e in encounters
    ]
    return templates.TemplateResponse(
        request, "encounters/history.html", {"user": user, "rows": rows}
    )


@router.get("/encounters/{encounter_id}", response_class=HTMLResponse, name="web-encounter")
def encounter_detail(
    request: Request,
    encounter_id: int,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Doctor's encounter view: vitals recorded so far + a diagnosis form."""
    repo = EncounterRepository(session)
    encounter = repo.get(encounter_id)
    if encounter is None or user.role is not Role.DOCTOR or encounter.doctor_id != user.id:
        # Keep it simple + safe: only the owning doctor sees the encounter page.
        from app.core.exceptions import PermissionDenied

        raise PermissionDenied("Not your encounter")
    return templates.TemplateResponse(
        request,
        "encounters/detail.html",
        {
            "user": user,
            "encounter": encounter,
            "vitals": repo.vitals_for_encounter(encounter_id),
            "diagnoses": repo.diagnoses_for_encounter(encounter_id),
            "medications": MedicationRepository(session).list(limit=100),
            "prescriptions": PrescriptionRepository(session).list_for_patient(encounter.patient_id),
            "medications_by_id": _med_names(session),
        },
    )


@router.post("/encounters/{encounter_id}/prescriptions", response_class=HTMLResponse,
             name="web-prescribe")
def prescribe(
    request: Request,
    encounter_id: int,
    medication_id: int = Form(...),
    dose: str = Form(...),
    refills: int = Form(0),
    override_interaction: bool = Form(False),
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """HTMX: prescribe within an encounter; swap back the prescriptions list.

    A §5.4 safety block re-renders the list partial with the block reason so the
    doctor sees exactly why (and can retry an interaction with override).
    """
    repo = EncounterRepository(session)
    encounter = repo.get(encounter_id)
    patient_id = encounter.patient_id if encounter is not None else None
    error = None
    try:
        prescription_service.prescribe(
            session, user.id, encounter_id, medication_id, dose, refills,
            override_interaction=override_interaction,
        )
    except AppError as exc:
        error = exc.message
        status_code = exc.http_status
    else:
        status_code = 200
    prescriptions = (
        PrescriptionRepository(session).list_for_patient(patient_id) if patient_id else []
    )
    return templates.TemplateResponse(
        request,
        "prescriptions/partials/list.html",
        {"prescriptions": prescriptions, "error": error, "medications_by_id": _med_names(session)},
        status_code=status_code,
    )


def _med_names(session: Session) -> dict[int, str]:
    """Map medication id -> name for rendering prescription rows."""
    return {m.id: m.name for m in MedicationRepository(session).list(limit=100)}


@router.get("/prescriptions", response_class=HTMLResponse, name="web-my-prescriptions")
def my_prescriptions(
    request: Request,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """A patient's own prescriptions list."""
    prescriptions = prescription_service.list_for_patient(session, user.id)
    return templates.TemplateResponse(
        request,
        "prescriptions/mine.html",
        {"user": user, "prescriptions": prescriptions, "medications_by_id": _med_names(session)},
    )


@router.post("/encounters/{encounter_id}/diagnoses", response_class=HTMLResponse,
             name="web-add-diagnosis")
def add_diagnosis(
    request: Request,
    encounter_id: int,
    icd_code: str = Form(...),
    description: str = Form(...),
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """HTMX: add a diagnosis and swap back the updated diagnoses list."""
    try:
        clinical_service.add_diagnosis(session, user.id, encounter_id, icd_code, description)
    except AppError as exc:
        return templates.TemplateResponse(
            request,
            "encounters/partials/diagnoses.html",
            {"diagnoses": EncounterRepository(session).diagnoses_for_encounter(encounter_id),
             "error": exc.message},
            status_code=exc.http_status,
        )
    return templates.TemplateResponse(
        request,
        "encounters/partials/diagnoses.html",
        {"diagnoses": EncounterRepository(session).diagnoses_for_encounter(encounter_id)},
    )
