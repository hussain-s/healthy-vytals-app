"""LLM providers — the vendor boundary, behind one small interface.

A *provider* is the thin thing that actually talks to a model and returns a
:class:`ProviderResult`. The client (``client.py``) depends only on this
interface, never on a vendor SDK, so HealthyVytals stays provider-agnostic and —
crucially for a local-first educational app — **runs with no SDK installed**.

Three providers, resolved by :func:`get_provider` from ``Settings.llm_provider``:

* ``"stub"`` (**default**, ADR-0006) — deterministic, offline, zero-dependency.
  Same input → same output, always. It is what makes the app boot and the whole
  test suite pass on a fresh clone with no API key and no ``anthropic``/``openai``
  package. Analogous to the SQLite default in ADR-0001.
* ``"anthropic"`` / ``"openai"`` — real providers. Their SDKs are **imported
  lazily inside the constructor**, so importing this module never requires them;
  you only need the package (and an API key) if you opt in via
  ``HV_LLM_PROVIDER``. Analogous to Postgres being opt-in.

The interface is intentionally minimal (one method, ``complete``) because that is
all the client needs; reliability, caching, routing, and observability live in the
client, not here, so every provider gets them for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.llm.errors import ProviderError


@dataclass(frozen=True)
class ProviderResult:
    """The normalized result of one provider call.

    ``text`` is the raw completion (which the client parses/validates against a
    schema when one was requested). ``is_refusal`` lets a provider signal "I
    declined / produced nothing usable" without raising, so the client can try a
    fallback. Token counts and ``stop_reason`` feed the observability record.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "stop"
    is_refusal: bool = False


class Provider(Protocol):
    """Structural interface every provider satisfies (duck-typed, no base class)."""

    def complete(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        max_tokens: int,
        timeout_s: float,
    ) -> ProviderResult:
        """Return a completion for ``prompt`` or raise :class:`ProviderError`."""
        ...


class StubProvider:
    """Deterministic, offline provider — the default (ADR-0006).

    It never touches the network and needs no SDK, yet it exercises every code
    path in the client (structured output, caching, retries, fallback) so tests
    and a fresh-clone demo are fully reproducible. It is a *teaching / test double*,
    not a model: given the same ``(model, system, prompt)`` it returns the same
    text every time.

    Behavior:
    * If the prompt embeds a JSON schema (the client asks for structured output),
      it returns a minimal JSON object populated from that schema's declared
      fields — enough to validate — so the whole structured path works offline.
    * Otherwise it echoes a short, deterministic acknowledgement of the prompt.
    Token counts are a simple word-count estimate, so cost/latency plumbing has
    non-zero numbers to carry.
    """

    def __init__(self, api_key: str | None = None) -> None:
        # Accepts an api_key for interface symmetry; ignores it (offline).
        self._api_key = api_key

    def complete(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        max_tokens: int,
        timeout_s: float,
    ) -> ProviderResult:
        import json

        text = self._stub_json(prompt) if '"properties"' in prompt else (
            f"[stub:{model}] acknowledged: {prompt[:80].strip()}"
        )
        in_tokens = len((system + prompt).split())
        out_tokens = len(text.split())
        return ProviderResult(
            text=text,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            stop_reason="stop",
        )

    @staticmethod
    def _stub_json(prompt: str) -> str:
        """Build a schema-valid JSON object from the schema embedded in the prompt.

        We locate the JSON schema the client embedded, then emit a deterministic
        value per declared property (typed by the schema): strings get a short
        placeholder, numbers a mid-range 0, arrays an empty list, etc. The result
        is valid against the contract, so the client's validation succeeds offline.
        """
        import json
        import re

        # Find the embedded schema object (the client marks it after "SCHEMA:").
        match = re.search(r"SCHEMA:\s*(\{.*\})\s*$", prompt, re.DOTALL)
        if not match:
            return "{}"
        try:
            schema = json.loads(match.group(1))
        except json.JSONDecodeError:
            return "{}"

        props: dict = schema.get("properties", {})
        defs: dict = schema.get("$defs", {})
        obj: dict[str, object] = {}
        for name, spec in props.items():
            obj[name] = StubProvider._stub_value(name, spec, defs)
        return json.dumps(obj)

    @staticmethod
    def _stub_value(name: str, spec: dict, defs: dict | None = None) -> object:
        """Deterministic placeholder value for one schema property.

        Resolves ``$ref``/``allOf`` into ``$defs`` so enum-typed fields (which
        Pydantic renders as a ``$ref`` to a definition, not an inline ``enum``)
        are populated with a valid member — otherwise a structured response with
        an enum field could never validate against the stub.
        """
        defs = defs or {}
        # Resolve a direct $ref or a single-item allOf wrapping a $ref.
        ref = spec.get("$ref")
        if not ref and isinstance(spec.get("allOf"), list) and len(spec["allOf"]) == 1:
            ref = spec["allOf"][0].get("$ref")
        if ref and ref.startswith("#/$defs/"):
            spec = defs.get(ref.split("/")[-1], {})

        # Honor enums first (pick the first option deterministically).
        enum = spec.get("enum")
        if enum:
            return enum[0]
        typ = spec.get("type")
        if typ == "array":
            return []
        if typ in ("number", "integer"):
            # Mid value if bounded, else 0 — deterministic and in-range.
            lo = spec.get("minimum", 0)
            hi = spec.get("maximum", lo)
            return round((lo + hi) / 2, 2) if typ == "number" else int((lo + hi) // 2)
        if typ == "boolean":
            return False
        return f"stub {name}"


def _require(pkg: str, provider: str) -> None:
    """Raise a clear, actionable error if an opt-in provider's SDK is missing."""
    import importlib.util

    if importlib.util.find_spec(pkg) is None:
        raise ProviderError(
            f"HV_LLM_PROVIDER={provider!r} requires the '{pkg}' package, which is "
            f"not installed. Install it (pip install {pkg}) or use the default "
            f"HV_LLM_PROVIDER=stub for offline/local development.",
            retryable=False,
        )


class AnthropicProvider:
    """Real Anthropic provider (opt-in). SDK imported lazily in the constructor."""

    def __init__(self, api_key: str) -> None:
        _require("anthropic", "anthropic")
        import anthropic  # lazy: only needed when this provider is selected

        if not api_key:
            raise ProviderError(
                "HV_LLM_PROVIDER=anthropic requires HV_ANTHROPIC_API_KEY to be set.",
                retryable=False,
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        max_tokens: int,
        timeout_s: float,
    ) -> ProviderResult:
        import anthropic

        try:
            msg = self._client.messages.create(
                model=model,
                system=system,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout_s,
            )
        except anthropic.APIStatusError as exc:  # pragma: no cover - needs live SDK
            status = getattr(exc, "status_code", 0)
            raise ProviderError(
                f"anthropic API error {status}: {exc}",
                retryable=status in (409, 429) or status >= 500,
            ) from exc
        except anthropic.APIError as exc:  # pragma: no cover - needs live SDK
            raise ProviderError(f"anthropic API error: {exc}", retryable=True) from exc

        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        usage = getattr(msg, "usage", None)
        return ProviderResult(
            text=text,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            stop_reason=getattr(msg, "stop_reason", "stop") or "stop",
            is_refusal=not text.strip(),
        )


class OpenAIProvider:
    """Real OpenAI provider (opt-in). SDK imported lazily in the constructor."""

    def __init__(self, api_key: str) -> None:
        _require("openai", "openai")
        import openai  # lazy

        if not api_key:
            raise ProviderError(
                "HV_LLM_PROVIDER=openai requires HV_OPENAI_API_KEY to be set.",
                retryable=False,
            )
        self._client = openai.OpenAI(api_key=api_key)

    def complete(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        max_tokens: int,
        timeout_s: float,
    ) -> ProviderResult:
        import openai

        try:
            resp = self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                timeout=timeout_s,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
        except openai.APIStatusError as exc:  # pragma: no cover - needs live SDK
            status = getattr(exc, "status_code", 0)
            raise ProviderError(
                f"openai API error {status}: {exc}",
                retryable=status in (409, 429) or status >= 500,
            ) from exc
        except openai.APIError as exc:  # pragma: no cover - needs live SDK
            raise ProviderError(f"openai API error: {exc}", retryable=True) from exc

        choice = resp.choices[0]
        text = choice.message.content or ""
        usage = getattr(resp, "usage", None)
        return ProviderResult(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            stop_reason=getattr(choice, "finish_reason", "stop") or "stop",
            is_refusal=not text.strip(),
        )


_PROVIDERS: dict[str, type] = {
    "stub": StubProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def get_provider(name: str, api_key: str | None = None) -> Provider:
    """Instantiate the configured provider by name.

    Raises :class:`ProviderError` for an unknown name (fail fast on misconfig,
    mirroring ``config._guard_production``'s philosophy) — never silently fall
    back to a different provider than the operator asked for.
    """
    try:
        cls = _PROVIDERS[name]
    except KeyError:
        raise ProviderError(
            f"Unknown HV_LLM_PROVIDER={name!r}. Valid: {', '.join(sorted(_PROVIDERS))}.",
            retryable=False,
        ) from None
    return cls(api_key)  # type: ignore[call-arg]
