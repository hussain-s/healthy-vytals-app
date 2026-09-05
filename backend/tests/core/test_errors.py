"""Tests for typed errors and their HTTP handlers (app.core.errors).

Confirms the semantic exception -> (status code, stable code, envelope) mapping
end-to-end by mounting throwaway routes that raise each error on a factory-built
app, and that request-validation failures use the same envelope.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import (
    AppError,
    Conflict,
    NotFound,
    PermissionDenied,
    register_exception_handlers,
)


class _SlotConflict(Conflict):
    """A domain-specific subclass to prove subclasses inherit handling + code override."""

    code = "slot_conflict"


class _Body(BaseModel):
    count: int


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A minimal app with the handlers registered and routes that raise errors."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom/not-found")
    def _not_found() -> None:
        raise NotFound("No such patient", details={"patient_id": 7})

    @app.get("/boom/forbidden")
    def _forbidden() -> None:
        raise PermissionDenied("Not your record")

    @app.get("/boom/conflict")
    def _conflict() -> None:
        raise _SlotConflict("That slot is taken")

    @app.get("/boom/base")
    def _base() -> None:
        raise AppError("Generic failure")

    @app.post("/echo")
    def _echo(body: _Body) -> dict[str, int]:
        return {"count": body.count}

    with TestClient(app) as test_client:
        yield test_client


def test_not_found_maps_to_404_with_stable_code_and_details(client: TestClient) -> None:
    response = client.get("/boom/not-found")
    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "No such patient",
        "details": {"patient_id": 7},
    }


def test_permission_denied_maps_to_403(client: TestClient) -> None:
    response = client.get("/boom/forbidden")
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_subclass_conflict_maps_to_409_with_overridden_code(client: TestClient) -> None:
    """A Conflict subclass inherits the 409 status but carries its own code."""
    response = client.get("/boom/conflict")
    assert response.status_code == 409
    assert response.json()["code"] == "slot_conflict"


def test_base_app_error_defaults_to_400(client: TestClient) -> None:
    response = client.get("/boom/base")
    assert response.status_code == 400
    assert response.json()["code"] == "error"


def test_request_validation_uses_same_envelope(client: TestClient) -> None:
    """Malformed request bodies produce the standard ErrorResponse shape."""
    response = client.post("/echo", json={"count": "not-an-int"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "request_validation_error"
    assert "errors" in body["details"]
