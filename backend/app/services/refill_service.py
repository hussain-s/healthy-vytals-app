"""Refill redemption service (NEW feature) — a patient uses one refill.

A patient redeems a refill against one of their active prescriptions: if refills
remain, the count is decremented by one and the redemption is audited (§5.7). When
the last refill is used the prescription stays active with zero refills remaining.

Orchestrated inside the caller's unit of work.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.repositories.prescription_repository import PrescriptionRepository
from app.services.audit_service import record_audit


class NoRefillsRemaining(Conflict):
    """A refill redemption was attempted with no refills left."""

    code = "no_refills_remaining"


def redeem_refill(session: Session, patient_id: int, prescription_id: int) -> int:
    """Redeem one refill on the patient's prescription; return refills remaining.

    Steps (in the caller's unit of work):
      1. Load the prescription (404 if missing); the patient must own it (403).
      2. Check that at least one refill remains; block otherwise (409).
      3. Decrement the refill count and audit ``prescription.redeem``.
    """
    rx_repo = PrescriptionRepository(session)
    prescription = rx_repo.get(prescription_id)
    if prescription is None:
        raise NotFound(f"No such prescription: {prescription_id}")
    if prescription.patient_id != patient_id:
        raise PermissionDenied("You may only redeem your own prescriptions")

    # Check that a refill is available, then consume it.
    remaining = prescription.refills
    if remaining <= 0:
        raise NoRefillsRemaining("No refills remaining on this prescription")

    prescription.refills = remaining - 1
    session.flush()

    record_audit(
        session,
        action="prescription.redeem",
        actor_id=patient_id,
        resource_type="prescription",
        resource_id=prescription_id,
        patient_id=patient_id,
    )
    return prescription.refills
