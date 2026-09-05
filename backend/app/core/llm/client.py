"""``LLMClient`` — the LLM as a system component (Chapter 2's five disciplines).

This is the one class services use to talk to a language model. It wraps a raw,
unreliable, non-deterministic provider call in the five engineering disciplines
that turn "a chat box" into "a dependency you can build on":

1. **Output contracts** — :meth:`analyze` returns a *validated* ``AssistantSchema``
   subclass, never free text. Invalid output is re-asked, then surfaced as a typed
   error, so a caller either gets a correct object or a clear failure.
2. **Reliability** — per-model retries with exponential backoff **and jitter**,
   a transparent **fallback model**, and a per-request **timeout**. Transient
   provider errors and schema-validation failures are retried; a refusal triggers
   the fallback; everything is bounded.
3. **Determinism** — an **input-hash cache** gives *effective determinism*:
   identical inputs return the identical result, even though the model itself is
   not deterministic (temperature is a dial, not a switch).
4. **Routing** — a ``tier`` (``"triage"`` vs ``"reasoning"``) selects a cheap/fast
   vs. capable model per call; routing is an architectural choice, not just cost.
5. **Observability** — every call emits one :class:`CallRecord` (model, tokens,
   latency, stop reason, cache hit, fallback, attempts) on every path.

The default provider is the deterministic **stub** (ADR-0006), so this class is
fully exercisable offline with no API key or vendor SDK — which is how the test
suite and a fresh-clone demo run. Point ``HV_LLM_PROVIDER`` at ``anthropic`` /
``openai`` to use a real model.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable
from typing import TypeVar

from app.core.config import get_settings
from app.core.llm.errors import LLMRefusal, ProviderError, SchemaValidationError
from app.core.llm.observability import CallRecord
from app.core.llm.providers import Provider, ProviderResult, get_provider
from app.core.llm.schemas import AssistantSchema

T = TypeVar("T", bound=AssistantSchema)


class LLMClient:
    """Provider-agnostic, production-shaped client for structured LLM calls.

    Construct once and reuse. All knobs default from :class:`Settings` so the app
    is configured in one place (``core/config``), but every knob is overridable
    for tests (notably ``provider=`` to inject a fake and ``sleep=`` to make
    backoff instant).
    """

    def __init__(
        self,
        *,
        provider: Provider | None = None,
        max_retries: int | None = None,
        timeout_s: float | None = None,
        enable_cache: bool | None = None,
        fallback_model: str | None = None,
        base_backoff_s: float = 0.2,
        max_backoff_s: float = 8.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        settings = get_settings()
        self._provider = provider or get_provider(
            settings.llm_provider, settings.llm_api_key
        )
        self._provider_name = settings.llm_provider
        self.max_retries = (
            settings.llm_max_retries if max_retries is None else max_retries
        )
        self.timeout_s = settings.llm_timeout_s if timeout_s is None else timeout_s
        self.enable_cache = (
            settings.llm_cache_enabled if enable_cache is None else enable_cache
        )
        self.fallback_model = (
            fallback_model
            if fallback_model is not None
            else (settings.llm_fallback_model or None)
        )
        self.base_backoff_s = base_backoff_s
        self.max_backoff_s = max_backoff_s
        self._sleep = sleep
        self._cache: dict[str, ProviderResult] = {}

    # -- public API -----------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        tier: str = "reasoning",
        system: str = "You are a helpful assistant.",
        max_tokens: int = 1024,
    ) -> str:
        """Return a free-text completion. Reliability + cache + observability apply."""
        result = self._call(
            prompt, tier=tier, system=system, max_tokens=max_tokens, schema=None
        )
        return result.text

    def analyze(
        self,
        content: str,
        schema: type[T],
        *,
        tier: str = "reasoning",
        system: str = "You are a precise clinical-support assistant.",
        instruction: str = "Analyze the following and respond as instructed.",
        max_tokens: int = 1024,
    ) -> T:
        """Return a validated instance of ``schema`` (the output contract).

        Builds a prompt that embeds ``schema``'s field contract, calls the model
        (with retries/fallback), then parses+validates the completion. Raises
        :class:`SchemaValidationError` if no attempt produced valid output, or
        :class:`LLMRefusal` if the model declined — never a partial object.
        """
        prompt = (
            f"{instruction}\n\n"
            f"Respond with ONLY a JSON object matching this schema "
            f"(no prose, no markdown fences).\n"
            f"CONTENT:\n{content}\n\n"
            f"SCHEMA: {schema.json_schema_for_prompt()}"
        )
        result = self._call(
            prompt, tier=tier, system=system, max_tokens=max_tokens, schema=schema
        )
        if result.is_refusal or not result.text.strip():
            raise LLMRefusal("model returned no usable output for the request")
        return self._parse(result.text, schema)

    # -- internals ------------------------------------------------------------

    def _call(
        self,
        prompt: str,
        *,
        tier: str,
        system: str,
        max_tokens: int,
        schema: type[AssistantSchema] | None,
    ) -> ProviderResult:
        """Resolve model → check cache → try primary → try fallback."""
        settings = get_settings()
        primary = settings.model_for_tier(tier)
        key = self._cache_key(primary, system, prompt, max_tokens, schema)

        if self.enable_cache and key in self._cache:
            cached = self._cache[key]
            CallRecord(
                model=primary,
                tier=tier,
                cache_hit=True,
                input_tokens=cached.input_tokens,
                output_tokens=cached.output_tokens,
                stop_reason=cached.stop_reason,
            ).log()
            return cached

        models = [primary]
        if self.fallback_model and self.fallback_model != primary:
            models.append(self.fallback_model)

        last_error: Exception | None = None
        for index, model in enumerate(models):
            try:
                result = self._call_with_retries(
                    model=model,
                    tier=tier,
                    system=system,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    schema=schema,
                    fallback_used=index > 0,
                )
            except (ProviderError, SchemaValidationError) as exc:
                last_error = exc
                continue  # exhausted this model; try the next in the chain

            if result.is_refusal and index < len(models) - 1:
                last_error = LLMRefusal("primary model refused; trying fallback")
                continue

            if self.enable_cache and not result.is_refusal:
                self._cache[key] = result
            return result

        # Every model in the chain failed. Preserve the *specific* failure type
        # (e.g. SchemaValidationError) so the caller can distinguish "the model
        # kept producing invalid output" from a transport error, per analyze()'s
        # contract. Only wrap when there is no typed cause to surface.
        if isinstance(last_error, (SchemaValidationError, ProviderError)):
            raise last_error
        raise ProviderError(
            f"all models failed ({', '.join(models)}): {last_error}",
            retryable=False,
        ) from last_error

    def _call_with_retries(
        self,
        *,
        model: str,
        tier: str,
        system: str,
        prompt: str,
        max_tokens: int,
        schema: type[AssistantSchema] | None,
        fallback_used: bool,
    ) -> ProviderResult:
        """Call one model, retrying transient + schema-validation failures."""
        attempt = 0
        while True:
            attempt += 1
            record = CallRecord(
                model=model, tier=tier, fallback_used=fallback_used, attempts=attempt
            )
            started = time.monotonic()
            try:
                result = self._provider.complete(
                    model=model,
                    system=system,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    timeout_s=self.timeout_s,
                )
                # If a schema was requested, validate here so a malformed body is
                # a retryable failure (a re-ask often fixes it), not a late crash.
                if schema is not None and not result.is_refusal:
                    self._parse(result.text, schema)
            except ProviderError as exc:
                record.latency_s = time.monotonic() - started
                record.error = f"ProviderError: {exc}"
                record.log()
                if not exc.retryable or attempt > self.max_retries:
                    raise
                self._sleep(self._backoff(attempt))
                continue
            except SchemaValidationError as exc:
                record.latency_s = time.monotonic() - started
                record.error = f"SchemaValidationError: {exc}"
                record.log()
                if attempt > self.max_retries:
                    raise
                self._sleep(self._backoff(attempt))
                continue

            record.latency_s = time.monotonic() - started
            record.input_tokens = result.input_tokens
            record.output_tokens = result.output_tokens
            record.stop_reason = result.stop_reason
            record.log()
            return result

    @staticmethod
    def _parse(text: str, schema: type[T]) -> T:
        """Validate ``text`` against ``schema`` or raise ``SchemaValidationError``.

        Tolerates a model that wraps JSON in prose/markdown by extracting the
        outermost ``{...}`` before validating — a small, common robustness win.
        """
        candidate = text.strip()
        if not candidate.startswith("{"):
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise SchemaValidationError("no JSON object found in model output")
            candidate = candidate[start : end + 1]
        try:
            return schema.model_validate_json(candidate)
        except ValueError as exc:  # pydantic ValidationError is a ValueError
            raise SchemaValidationError(f"output did not match schema: {exc}") from exc

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with **full jitter**, capped at ``max_backoff_s``.

        Full jitter (a uniform draw in ``[0, ceiling]``) prevents a thundering
        herd of synchronized retries from hammering a recovering provider — the
        AWS/Google-SRE recommended strategy.
        """
        ceiling = min(self.max_backoff_s, self.base_backoff_s * (2 ** (attempt - 1)))
        return random.uniform(0, ceiling)

    @staticmethod
    def _cache_key(
        model: str,
        system: str,
        prompt: str,
        max_tokens: int,
        schema: type[AssistantSchema] | None,
    ) -> str:
        """Stable SHA-256 of everything that affects the output.

        ``sort_keys`` guarantees identical inputs hash identically regardless of
        dict ordering — the basis of effective determinism (discipline 3).
        """
        payload = json.dumps(
            {
                "model": model,
                "system": system,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "schema": schema.__name__ if schema else None,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
