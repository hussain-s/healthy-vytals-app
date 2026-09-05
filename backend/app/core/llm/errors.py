"""Typed failures for the LLM component layer.

These extend the app's :class:`~app.core.exceptions.AppError` family so an LLM
failure that reaches a router maps to an HTTP status centrally (``core/errors``),
exactly like every other domain/application error — no bespoke handling.

Why a dedicated set of types (not bare ``Exception``): the client's reliability
logic (``client.py``) must distinguish *transient* failures worth retrying from
*permanent* ones, and a *refusal* (the model declined) from a *crash*. Callers,
in turn, want to catch "the model wouldn't/couldn't answer" without catching
programmer errors. Encoding that in the type is clearer and safer than string
matching on messages.
"""

from __future__ import annotations

from app.core.exceptions import AppError


class LLMError(AppError):
    """Base class for anything that goes wrong talking to the language model.

    A 502 by default: from the client's perspective the model is an upstream
    dependency, so a failure there is a bad-gateway condition, not the caller's
    fault (400) — subclasses refine this where a different status fits better.
    """

    code = "llm_error"
    http_status = 502


class ProviderError(LLMError):
    """The underlying provider call failed (network, HTTP, SDK, or bad request).

    Carries ``retryable`` so the client's retry loop can tell a transient 429/503
    (worth backing off and retrying) from a permanent 400 (retrying is pointless).
    Providers raise this instead of leaking vendor-specific exception types, so
    the client stays provider-agnostic.
    """

    code = "llm_provider_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.retryable = retryable


class SchemaValidationError(LLMError):
    """The model returned text that does not satisfy the requested schema.

    Treated as *retryable* by the client (a re-ask often yields valid output),
    but if every attempt fails the client surfaces this so the caller never
    receives a half-parsed object. Maps to 502: the fault is the upstream model's,
    not the caller's input.
    """

    code = "llm_schema_validation_error"


class LLMRefusal(LLMError):
    """The model declined to answer (safety filter, policy, or empty completion).

    A refusal is **not** an error in the transport sense — the call succeeded — so
    it is a distinct type. The client may try a fallback model; if none complies,
    the caller decides how to degrade (for the vitals assistant: fall back to the
    deterministic rule-based flags alone). Maps to 422: no usable answer was
    produced for this request.
    """

    code = "llm_refusal"
    http_status = 422
