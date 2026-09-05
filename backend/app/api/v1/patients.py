"""Patient-scoped read endpoints (v1) — currently the vitals time series (M10).

Thin controller over ``clinical_service``: it performs the coarse authenticated
gate and hands off to the service, which enforces the fine-grained history
authorization (§5.3) and consent gate (§5.8) and audits the read. The returned
series powers the vitals trend chart (ADR-0007) and is reusable by any API client.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.encounter import VitalsPoint, VitalsSeriesOut
from app.services import clinical_service

router = APIRouter(prefix="/patients", tags=["clinical"])


@router.get(
    "/{patient_id}/vitals-series",
    response_model=VitalsSeriesOut,
    summary="A patient's vitals over time (for trend charts)",
)
def vitals_series(
    patient_id: int,
    viewer: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> VitalsSeriesOut:
    """Return the patient's vitals as time-ordered points.

    Authorization + consent scoping + audit are enforced in
    ``clinical_service.get_vitals_series`` (same rules as reading history): a
    patient sees only their own; a doctor needs a treating relationship; a nurse
    may read; an admin may not.
    """
    rows = clinical_service.get_vitals_series(
        session, viewer.id, viewer.role, patient_id
    )
    points = [
        VitalsPoint(
            recorded_at=v.created_at,
            heart_rate=v.heart_rate,
            resp_rate=v.resp_rate,
            systolic_bp=v.systolic_bp,
            temp_c=v.temp_c,
            spo2=v.spo2,
        )
        for v in rows
    ]
    return VitalsSeriesOut(patient_id=patient_id, points=points)
