"""LLM component layer — the app's typed, reliable interface to a language model.

This package is HealthyVytals' answer to a simple problem: a raw LLM call is not
a system dependency you can build on. It returns free text of unpredictable shape,
it fails over the network, and it is non-deterministic. Everything under
``core/llm`` wraps that raw call so the rest of the app can treat the model the
way it treats the database or the JWT layer — a component with a **contract**,
**reliability**, **determinism**, **routing**, and **observability**.

Layering (ADR-0004): this is cross-cutting infrastructure, like ``core/security``.
Services call :class:`~app.core.llm.client.LLMClient`; the pure ``domain/`` layer
never imports it. Providers are resolved lazily, and the default provider is a
deterministic **stub** (ADR-0006), so the app and its test suite run on a fresh
clone with **no API key and no vendor SDK installed** — exactly mirroring the
SQLite-default/Postgres-opt-in choice in ADR-0001.

Public surface (import from here):
    LLMClient       — the client services use
    CallRecord      — the per-call observability record
    AssistantSchema — base for structured-output contracts
    LLMError, SchemaValidationError, ProviderError, LLMRefusal — typed failures
"""

from __future__ import annotations

from app.core.llm.client import LLMClient
from app.core.llm.errors import (
    LLMError,
    LLMRefusal,
    ProviderError,
    SchemaValidationError,
)
from app.core.llm.observability import CallRecord
from app.core.llm.schemas import AssistantSchema

__all__ = [
    "LLMClient",
    "CallRecord",
    "AssistantSchema",
    "LLMError",
    "LLMRefusal",
    "ProviderError",
    "SchemaValidationError",
]
