"""Tests for the LLM component layer (app.core.llm) — Chapter 2's five disciplines.

All tests run **offline**: they either inject a fake provider or use the default
deterministic stub, so no API key or vendor SDK is required (ADR-0006). ``sleep``
is stubbed to a no-op so retry/backoff paths run instantly.
"""

from __future__ import annotations

import pytest
from pydantic import Field

from app.core.config import get_settings
from app.core.llm.client import LLMClient
from app.core.llm.errors import LLMRefusal, ProviderError, SchemaValidationError
from app.core.llm.observability import CallRecord, CallStats
from app.core.llm.providers import ProviderResult, StubProvider, get_provider
from app.core.llm.schemas import AssistantSchema


class _Explanation(AssistantSchema):
    summary: str = Field(description="One-line summary.")
    score: int = Field(ge=0, le=10, description="A 0..10 score.")
    tags: list[str] = Field(default_factory=list, description="Zero or more tags.")


class _ScriptedProvider:
    """A fake provider that returns/raises a scripted sequence, recording calls."""

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls: list[dict] = []

    def complete(self, **kwargs) -> ProviderResult:
        self.calls.append(kwargs)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _client(provider, **kw) -> LLMClient:
    kw.setdefault("sleep", lambda _s: None)  # make backoff instant
    kw.setdefault("enable_cache", False)
    return LLMClient(provider=provider, **kw)


# --- Discipline 1: output contracts ------------------------------------------

def test_analyze_returns_validated_schema_from_stub() -> None:
    """The default stub yields a schema-valid object offline — no network/SDK."""
    client = _client(StubProvider())
    result = client.analyze("resting heart rate 190 for a 40-year-old", _Explanation)
    assert isinstance(result, _Explanation)
    assert 0 <= result.score <= 10  # respected the schema bounds


def test_invalid_json_is_retried_then_raised() -> None:
    """Malformed output is retried; if it never validates, a typed error surfaces."""
    provider = _ScriptedProvider(
        [ProviderResult(text="not json")] * 3  # 1 try + 2 retries
    )
    client = _client(provider, max_retries=2)
    with pytest.raises(SchemaValidationError):
        client.analyze("x", _Explanation)
    assert len(provider.calls) == 3  # exhausted the retry budget


def test_invalid_then_valid_recovers_within_retry_budget() -> None:
    """A re-ask that finally returns valid JSON succeeds without raising."""
    provider = _ScriptedProvider(
        [
            ProviderResult(text="oops"),
            ProviderResult(text='{"summary":"ok","score":3,"tags":[]}'),
        ]
    )
    client = _client(provider, max_retries=2)
    out = client.analyze("x", _Explanation)
    assert out.summary == "ok" and out.score == 3
    assert len(provider.calls) == 2


def test_parse_extracts_json_wrapped_in_prose() -> None:
    """Robustness: JSON wrapped in prose/markdown is still extracted and validated."""
    provider = _ScriptedProvider(
        [ProviderResult(text='Sure!\n```json\n{"summary":"s","score":1,"tags":["a"]}\n```')]
    )
    out = _client(provider).analyze("x", _Explanation)
    assert out.tags == ["a"]


# --- Discipline 2: reliability (retry + backoff + fallback + timeout) --------

def test_transient_provider_error_is_retried() -> None:
    """A retryable ProviderError backs off and retries, then succeeds."""
    provider = _ScriptedProvider(
        [
            ProviderError("429 rate limited", retryable=True),
            ProviderResult(text="hello"),
        ]
    )
    text = _client(provider, max_retries=2).complete("hi")
    assert text == "hello"
    assert len(provider.calls) == 2


def test_non_retryable_error_is_not_retried() -> None:
    """A permanent (non-retryable) error fails fast without burning the budget."""
    provider = _ScriptedProvider([ProviderError("400 bad request", retryable=False)])
    with pytest.raises(ProviderError):
        _client(provider, max_retries=5).complete("hi")
    assert len(provider.calls) == 1


def test_fallback_model_used_when_primary_exhausts_retries() -> None:
    """When the primary model keeps failing, the fallback model answers."""
    provider = _ScriptedProvider(
        [
            ProviderError("boom", retryable=True),
            ProviderError("boom", retryable=True),
            ProviderError("boom", retryable=True),  # primary: 1 try + 2 retries
            ProviderResult(text="from-fallback"),   # fallback model
        ]
    )
    client = _client(provider, max_retries=2, fallback_model="stub-fallback")
    assert client.complete("hi") == "from-fallback"
    # last call routed to the fallback model id
    assert provider.calls[-1]["model"] == "stub-fallback"


def test_refusal_triggers_fallback_then_raises_if_all_refuse() -> None:
    """A refusal (not an error) tries the fallback; if all refuse, LLMRefusal."""
    provider = _ScriptedProvider(
        [
            ProviderResult(text="", is_refusal=True),
            ProviderResult(text="", is_refusal=True),
        ]
    )
    client = _client(provider, max_retries=0, fallback_model="stub-fallback")
    with pytest.raises(LLMRefusal):
        client.analyze("x", _Explanation)


# --- Discipline 3: determinism (input-hash cache) ----------------------------

def test_cache_returns_identical_result_and_skips_provider() -> None:
    """Identical inputs hit the cache: same object, provider called only once."""
    provider = _ScriptedProvider([ProviderResult(text="once")])
    client = _client(provider, enable_cache=True)
    first = client.complete("same prompt")
    second = client.complete("same prompt")
    assert first == second == "once"
    assert len(provider.calls) == 1  # second served from cache


def test_stub_is_deterministic() -> None:
    """Same input → same output from the stub (the basis for reproducible demos)."""
    a = _client(StubProvider()).complete("explain retries")
    b = _client(StubProvider()).complete("explain retries")
    assert a == b


# --- Discipline 4: routing ---------------------------------------------------

def test_tier_routing_selects_configured_model() -> None:
    """The tier picks the configured model id; unknown tiers degrade to reasoning."""
    settings = get_settings()
    provider = _ScriptedProvider(
        [ProviderResult(text="t"), ProviderResult(text="r")]
    )
    client = _client(provider)
    client.complete("x", tier="triage")
    client.complete("y", tier="reasoning")
    assert provider.calls[0]["model"] == settings.llm_model_triage
    assert provider.calls[1]["model"] == settings.llm_model_reasoning


# --- Discipline 5: observability ---------------------------------------------

def test_call_record_logs_on_success(caplog: pytest.LogCaptureFixture) -> None:
    """Every call emits a structured telemetry line."""
    with caplog.at_level("INFO", logger="healthyvytals.llm"):
        _client(StubProvider()).complete("hi")
    assert any("llm_call" in r.message for r in caplog.records)


def test_call_stats_aggregate() -> None:
    """CallStats folds records into running totals for a future dashboard/tests."""
    stats = CallStats()
    stats.add(CallRecord(model="m", tier="triage", input_tokens=3, output_tokens=2))
    stats.add(CallRecord(model="m", tier="triage", cache_hit=True))
    assert stats.calls == 2 and stats.cache_hits == 1 and stats.total_input_tokens == 3


# --- Providers ---------------------------------------------------------------

def test_get_provider_unknown_name_fails_fast() -> None:
    with pytest.raises(ProviderError):
        get_provider("gemini")


def test_opt_in_provider_without_sdk_gives_actionable_error() -> None:
    """Selecting a real provider without its SDK installed fails with guidance."""
    # anthropic/openai are not installed in the offline test env.
    with pytest.raises(ProviderError) as exc:
        get_provider("anthropic", api_key="sk-x")
    assert "not installed" in str(exc.value) or "requires" in str(exc.value)
