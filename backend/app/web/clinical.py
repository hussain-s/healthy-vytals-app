"""Web (HTML/HTMX) clinical screens: patient history and doctor encounter actions.

Thin presentation over clinical_service (DESIGN §7.6, rule 7). Scoping and
immutability live in the service; these routes render what the caller is allowed
to see. v1 scope: a patient's own history view, and a doctor's encounter page
(record a diagnosis via HTMX). Vitals entry for nurses reuses the same pattern.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, PermissionDenied
from app.core.roles import Role
from app.db.session import get_session
from app.domain.appointment_state import Transition
from app.domain.vitals_ranges import VitalsReading
from app.models.user import User
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.encounter_repository import EncounterRepository
from app.repositories.lab_repository import LabOrderRepository, LabResultRepository
from app.repositories.prescription_repository import (
    MedicationRepository,
    PrescriptionRepository,
)
from app.services import (
    appointment_service,
    clinical_service,
    lab_service,
    prescription_service,
)
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


@router.post("/appointments/{appointment_id}/open", name="web-open-encounter")
def open_encounter_from_appointment(
    appointment_id: int,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Doctor action: open (or resume) the encounter for an appointment, then go to it.

    Delegates to clinical_service.open_encounter (idempotent, owning-doctor check),
    then redirects to the encounter page. Non-doctors are rejected by the service.
    """
    if user.role is not Role.DOCTOR:
        from app.core.exceptions import PermissionDenied

        raise PermissionDenied("Only doctors open encounters")
    encounter = clinical_service.open_encounter(session, user.id, appointment_id)
    return RedirectResponse(
        url=f"/clinical/encounters/{encounter.id}", status_code=303
    )


@router.post("/appointments/{appointment_id}/check-in", name="web-check-in")
def check_in(
    appointment_id: int,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Nurse action: check a patient in (advances the appointment state). Back to board."""
    if user.role is not Role.NURSE:
        raise PermissionDenied("Only nurses check patients in")
    appointment_service.change_status(
        session, user.id, user.role, appointment_id, Transition.CHECK_IN
    )
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/appointments/{appointment_id}/vitals", response_class=HTMLResponse,
            name="web-vitals-form")
def vitals_form(
    request: Request,
    appointment_id: int,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Nurse triage: the vitals-entry form for an appointment."""
    if user.role is not Role.NURSE:
        raise PermissionDenied("Only nurses record vitals here")
    appt = AppointmentRepository(session).get(appointment_id)
    if appt is None:
        from app.core.exceptions import NotFound

        raise NotFound("No such appointment")
    return templates.TemplateResponse(
        request, "encounters/vitals_form.html", {"user": user, "appointment": appt},
    )


@router.post("/appointments/{appointment_id}/vitals", name="web-vitals-submit")
def vitals_submit(
    request: Request,
    appointment_id: int,
    heart_rate: str = Form(""),
    resp_rate: str = Form(""),
    systolic_bp: str = Form(""),
    temp_c: str = Form(""),
    spo2: str = Form(""),
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Nurse triage: record vitals for the appointment; render the flagged result.

    Empty fields are treated as 'not measured' (None). Delegates to
    clinical_service.record_vitals_for_appointment, which ensures the encounter
    exists and runs the age-based flagging.
    """
    if user.role is not Role.NURSE:
        raise PermissionDenied("Only nurses record vitals here")

    def _int(v: str) -> int | None:
        v = v.strip()
        return int(v) if v else None

    def _float(v: str) -> float | None:
        v = v.strip()
        return float(v) if v else None

    reading = VitalsReading(
        heart_rate=_int(heart_rate), resp_rate=_int(resp_rate),
        systolic_bp=_int(systolic_bp), temp_c=_float(temp_c), spo2=_int(spo2),
    )
    vitals = clinical_service.record_vitals_for_appointment(
        session, user.id, appointment_id, reading
    )
    return templates.TemplateResponse(
        request, "encounters/partials/vitals_result.html", {"vitals": vitals},
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
            "lab_rows": _lab_rows_for_encounter(session, encounter_id),
        },
    )


def _lab_rows_for_encounter(session: Session, encounter_id: int) -> list[dict]:
    """Lab orders on an encounter, each with its results (for the encounter page)."""
    orders = LabOrderRepository(session)
    results = LabResultRepository(session)
    return [
        {"order": o, "results": results.list_for_order(o.id)}
        for o in orders.list_for_encounter(encounter_id)
    ]


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


# --- Labs (M8 web UI) ---


@router.post("/encounters/{encounter_id}/labs", response_class=HTMLResponse,
             name="web-order-lab")
def order_lab(
    request: Request,
    encounter_id: int,
    test_code: str = Form(...),
    test_name: str = Form(...),
    notes: str = Form(""),
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """HTMX: doctor orders a lab on the encounter; swap back the lab list."""
    error = None
    try:
        lab_service.order_lab(session, user.id, encounter_id, test_code, test_name, notes or None)
    except AppError as exc:
        error = exc.message
        status_code = exc.http_status
    else:
        status_code = 200
    return templates.TemplateResponse(
        request,
        "labs/partials/order_list.html",
        {"lab_rows": _lab_rows_for_encounter(session, encounter_id), "error": error},
        status_code=status_code,
    )


@router.get("/labs", response_class=HTMLResponse, name="web-my-labs")
def my_labs(
    request: Request,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """A patient's own lab orders + results (service-scoped)."""
    rows = lab_service.get_patient_labs(session, user.id, user.role, user.id)
    return templates.TemplateResponse(
        request, "labs/mine.html", {"user": user, "lab_rows": rows},
    )


@router.get("/labs/queue", response_class=HTMLResponse, name="web-lab-queue")
def lab_queue(
    request: Request,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Nurse work queue: orders still awaiting results."""
    if user.role is not Role.NURSE:
        raise PermissionDenied("Only nurses see the lab queue")
    pending = LabOrderRepository(session).pending()
    return templates.TemplateResponse(
        request, "labs/queue.html", {"user": user, "orders": pending},
    )


@router.post("/labs/{lab_order_id}/results", response_class=HTMLResponse,
             name="web-record-lab-result")
def record_lab_result(
    request: Request,
    lab_order_id: int,
    analyte: str = Form(...),
    value: float = Form(...),
    unit: str = Form(""),
    reference_low: str = Form(""),
    reference_high: str = Form(""),
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """HTMX (nurse/doctor): record a result value; swap back the result list."""
    def _f(v: str) -> float | None:
        v = v.strip()
        return float(v) if v else None

    error = None
    try:
        lab_service.record_result(
            session, user.id, user.role, lab_order_id, analyte, value,
            unit or None, _f(reference_low), _f(reference_high),
        )
    except AppError as exc:
        error = exc.message
        status_code = exc.http_status
    else:
        status_code = 200
    return templates.TemplateResponse(
        request,
        "labs/partials/result_list.html",
        {"results": LabResultRepository(session).list_for_order(lab_order_id),
         "order_id": lab_order_id, "error": error},
        status_code=status_code,
    )
