"""Per-call observability for the LLM layer (Chapter 2, discipline 5).

You cannot improve — or bill, or debug — what you cannot see. Every call through
:class:`~app.core.llm.client.LLMClient` emits one :class:`CallRecord` capturing
what happened: which model and tier ran, how many tokens in/out, how long it
took, why it stopped, whether the cache served it, whether the fallback fired,
and how many attempts it needed.

This is deliberately a *logging* record, not the audit trail. ``audit_service``
records **PHI/security actions** for compliance (ADR-0005); this records
**operational telemetry** for cost/latency/reliability. They answer different
questions and must not be conflated (see ADR-0006, "Alternatives considered").
A service that wants both emits a ``CallRecord`` *and* an ``llm.*`` audit row.

The record is emitted to the standard library ``logging`` (logger name
``"healthyvytals.llm"``) as structured ``key=value`` pairs, so it works with no
extra dependency and is easy to grep or ship to a real sink later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("healthyvytals.llm")


@dataclass
class CallRecord:
    """One line of telemetry for a single logical LLM call.

    Fields default to a benign "nothing happened yet" state so the client can
    build the record incrementally and always emit *something*, even on the error
    path. ``log()`` is called exactly once per call, on every path (cache hit,
    success, or failure).
    """

    model: str
    tier: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    stop_reason: str = ""
    cache_hit: bool = False
    fallback_used: bool = False
    attempts: int = 1
    error: str = ""

    @property
    def total_tokens(self) -> int:
        """Sum of prompt + completion tokens — the basis for a cost estimate."""
        return self.input_tokens + self.output_tokens

    def log(self) -> None:
        """Emit this record as one structured log line.

        Failures log at WARNING (they need attention); everything else at INFO.
        The format is stable ``key=value`` pairs so it stays greppable and can be
        parsed by a log shipper without changing call sites.
        """
        line = (
            f"llm_call model={self.model} tier={self.tier} "
            f"input_tokens={self.input_tokens} output_tokens={self.output_tokens} "
            f"total_tokens={self.total_tokens} latency_s={self.latency_s:.3f} "
            f"stop_reason={self.stop_reason or '-'} cache_hit={self.cache_hit} "
            f"fallback_used={self.fallback_used} attempts={self.attempts}"
        )
        if self.error:
            logger.warning("%s error=%s", line, self.error)
        else:
            logger.info(line)


@dataclass
class CallStats:
    """Optional in-process aggregate of many :class:`CallRecord`s.

    Handy for tests and a future dashboard: total calls, cache hits, tokens, and
    cumulative estimated spend. Not wired into the client by default (the client
    only *emits* records); a caller that wants running totals can accumulate them.
    """

    calls: int = 0
    cache_hits: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    errors: int = 0
    _records: list[CallRecord] = field(default_factory=list, repr=False)

    def add(self, record: CallRecord) -> None:
        """Fold one record into the running totals."""
        self.calls += 1
        self.cache_hits += 1 if record.cache_hit else 0
        self.total_input_tokens += record.input_tokens
        self.total_output_tokens += record.output_tokens
        self.errors += 1 if record.error else 0
        self._records.append(record)
