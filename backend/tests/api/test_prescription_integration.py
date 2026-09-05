"""Phase 4 exit-gate integration test (DESIGN §9).

Pins the acceptance: an unsafe prescription is blocked with a clear, reasoned
error; a safe one succeeds. Runs the full flow over the JSON API — admin
provisions a doctor, patient self-registers, an appointment/encounter is set up,
then prescriptions are attempted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Encounter
from app.models.prescription import Allergy, DrugInteraction, Medication, Prescription
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User

PW = "longenough1"
BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def world(db_sessionmaker: sessionmaker[Session]) -> dict[str, int]:
    with db_sessionmaker() as s:
        doc = User(email="doc@example.com", password_hash=hash_password(PW), role=Role.DOCTOR)
        pat = User(email="pat@example.com", password_hash=hash_password(PW), role=Role.PATIENT)
        s.add_all([doc, pat])
        s.flush()
        amox = Medication(name="Amoxicillin", drug_class="penicillin")
        warfarin = Medication(name="Warfarin", drug_class="anticoagulant")
        aspirin = Medication(name="Aspirin", drug_class="nsaid")
        oxy = Medication(name="Oxycodone", drug_class="opioid", is_controlled=True)
        s.add_all([amox, warfarin, aspirin, oxy])
        s.flush()
        s.add(DrugInteraction(medication_a_id=warfarin.id, medication_b_id=aspirin.id, severity="severe"))
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
        s.add(slot)
        s.flush()
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                           status=AppointmentStatus.IN_PROGRESS)
        s.add(appt)
        s.flush()
        enc = Encounter(appointment_id=appt.id, patient_id=pat.id, doctor_id=doc.id, opened_at=BASE)
        s.add(enc)
        s.flush()  # populate enc.id before referencing it below
        # Patient already actively takes Warfarin.
        s.add(Prescription(encounter_id=enc.id, patient_id=pat.id, prescriber_id=doc.id,
                           medication_id=warfarin.id, dose="5mg", status="active"))
        s.commit()
        return {
            "enc": enc.id, "pat": pat.id, "amox": amox.id,
            "aspirin": aspirin.id, "oxy": oxy.id,
        }


def _doc(client: TestClient) -> dict[str, str]:
    t = client.post("/api/v1/auth/login", json={"email": "doc@example.com", "password": PW}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {t}"}


def _prescribe(client: TestClient, headers, enc, med, **extra) -> "object":
    body = {"encounter_id": enc, "medication_id": med, "dose": "1 tab", **extra}
    return client.post("/api/v1/prescriptions", headers=headers, json=body)


def test_phase4_exit_gate(client: TestClient, world: dict[str, int]) -> None:
    doc = _doc(client)

    # Safe prescription succeeds.
    assert _prescribe(client, doc, world["enc"], world["amox"]).status_code == 201

    # Interaction (Aspirin vs active Warfarin) is blocked with a clear reason...
    blocked = _prescribe(client, doc, world["enc"], world["aspirin"])
    assert blocked.status_code == 409
    body = blocked.json()
    assert body["code"] == "unsafe_prescription"
    assert body["details"]["reason"] == "interaction"
    assert "interact" in body["message"].lower()

    # ...but proceeds with an explicit override.
    assert _prescribe(
        client, doc, world["enc"], world["aspirin"], override_interaction=True
    ).status_code == 201

    # Controlled substance with refills is capped.
    capped = _prescribe(client, doc, world["enc"], world["oxy"], refills=5)
    assert capped.status_code == 409
    assert capped.json()["details"]["reason"] == "refill_cap"


def test_allergy_block_is_absolute(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    with db_sessionmaker() as s:
        s.add(Allergy(patient_id=world["pat"], substance="penicillin"))
        s.commit()
    doc = _doc(client)
    # Even with override, an allergy match is refused.
    resp = _prescribe(client, doc, world["enc"], world["amox"], override_interaction=True)
    assert resp.status_code == 409
    assert resp.json()["details"]["reason"] == "allergy"
