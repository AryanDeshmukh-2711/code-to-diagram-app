"""Per-call accounting: task, tokens, latency, cost, user.

NFR-M3 wants per-run cost attributable to a user. The expensive runs are the
ones that fail — a run that burns two full generations and then raises is
exactly the run you cannot afford to have missing from the ledger — so every
attempt is recorded, including failures, before the error propagates.

The sink is injectable so the API can persist records against GenerationRun
(SRS §6.2) without the gateway knowing anything about the database.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

logger = logging.getLogger("llm.calls")

Outcome = Literal["ok", "schema_invalid", "provider_error"]


@dataclass(frozen=True)
class CallRecord:
    """One provider call. One of these exists per attempt, not per run."""

    task: str
    provider: str
    model: str
    attempt: int
    outcome: Outcome
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: Decimal | None
    user_id: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class CallSink(Protocol):
    """Where call records go."""

    def record(self, record: CallRecord) -> None: ...


class LoggingSink:
    """Default sink: one structured log line per call."""

    def record(self, record: CallRecord) -> None:
        logger.info(
            "llm_call task=%s provider=%s model=%s attempt=%d outcome=%s "
            "input_tokens=%d output_tokens=%d latency_ms=%.1f cost_usd=%s user_id=%s",
            record.task,
            record.provider,
            record.model,
            record.attempt,
            record.outcome,
            record.input_tokens,
            record.output_tokens,
            record.latency_ms,
            "unmeasured" if record.cost_usd is None else f"{record.cost_usd:.6f}",
            record.user_id or "-",
        )


class RecordingSink:
    """In-memory sink, for tests and for aggregating a single run."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    def record(self, record: CallRecord) -> None:
        self.records.append(record)

    @property
    def total_cost_usd(self) -> Decimal | None:
        """Summed cost, or None if any call in the run was unmeasured.

        Deliberately not "sum of what we know" — a partial total presented as a
        total is how a run looks cheaper than it was.
        """
        if any(r.cost_usd is None for r in self.records):
            return None
        return sum((r.cost_usd for r in self.records), Decimal(0))
