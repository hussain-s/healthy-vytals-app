"""Output-contract base for LLM responses (Chapter 2, discipline 1).

A raw LLM returns free text. The rest of the app cannot build on "sometimes a
paragraph, sometimes a list" — services need a *validated object* with known
fields. Every structured response therefore subclasses :class:`AssistantSchema`,
which is a thin Pydantic ``BaseModel`` with two conveniences the client relies on:

* :meth:`json_schema_for_prompt` — the field contract, rendered compactly for
  inclusion in the prompt so the model knows exactly what shape to return.
* :meth:`model_validate_json` (inherited from Pydantic) — the parse+validate step
  the client runs on the model's text; a failure here raises
  :class:`~app.core.llm.errors.SchemaValidationError` and triggers a re-ask.

Keeping this in ``core/llm`` (not ``schemas/``, which holds API request/response
models) reflects the layering: these are the *model's* output contracts, an
infrastructure concern, distinct from the HTTP wire schemas services map to.
"""

from __future__ import annotations

import json

from pydantic import BaseModel


class AssistantSchema(BaseModel):
    """Base class for a structured, validated LLM response.

    Subclasses declare their fields with types and ``Field(description=...)``; the
    descriptions double as instructions to the model via
    :meth:`json_schema_for_prompt`. Pydantic then enforces the contract on parse,
    so a service either gets a fully-valid instance or a typed error — never a
    half-populated object.
    """

    @classmethod
    def json_schema_for_prompt(cls) -> str:
        """Return a compact JSON schema string to embed in the prompt.

        We hand the model the field names, types, and descriptions so it can fill
        the contract. This is provider-neutral: providers that support native
        constrained/structured output can use the same schema; the stub and any
        text-only provider rely on this prompt instruction plus post-hoc
        validation. Compact (no indentation) to spend as few tokens as possible.
        """
        return json.dumps(cls.model_json_schema(), separators=(",", ":"))
