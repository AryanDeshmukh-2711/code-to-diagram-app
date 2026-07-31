"""Every PRD section 9 metric, as a query over the event log.

Nothing here is precomputed. Each number is a SELECT that can be run by hand,
argued with, and re-run against a changed definition — which matters because
the definitions themselves are the hypotheses being tested. "Exported with
zero regeneration" is a target of 60%; if it comes in at 30% the useful next
question is whether the metric or the product is wrong, and that question is
only answerable when the metric is a visible query rather than a counter
someone incremented eighteen months ago.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from analytics.events import (
    CPM_CONFIRMED,
    EXPORT_COMPLETED,
    FUNNEL,
    PROJECT_CREATED,
    RUN_STARTED,
    SIGNUP,
)
from analytics.review_signals import EDITED, RUBBER_STAMPED, UNKNOWN, VERIFIED, interpret
from store.session import SessionFactory

# make_interval rather than string concatenation: asyncpg infers the type of a
# parameter from its use, and ":days || ' days'" makes it infer text, which
# then refuses the integer it is given.
WINDOW = "make_interval(days => :days)"


@dataclass(frozen=True)
class FunnelStep:
    name: str
    accounts: int
    from_previous_pct: float | None
    from_start_pct: float | None
    dropped: int


@dataclass(frozen=True)
class Metrics:
    days: int
    funnel: list[FunnelStep] = field(default_factory=list)
    time_to_first_export: dict[str, Any] = field(default_factory=dict)
    clean_export_rate: dict[str, Any] = field(default_factory=dict)
    diagram_failures: list[dict[str, Any]] = field(default_factory=list)
    run_cost: dict[str, Any] = field(default_factory=dict)
    review: dict[str, Any] = field(default_factory=dict)
    edit_distribution: list[dict[str, Any]] = field(default_factory=list)


FUNNEL_SQL = """
SELECT name, count(DISTINCT account_id) AS accounts
FROM events
WHERE occurred_at >= now() - make_interval(days => :days)
  AND name = ANY(:names)
GROUP BY name
"""

TIME_TO_FIRST_EXPORT_SQL = """
WITH first_signup AS (
    SELECT account_id, min(occurred_at) AS started
    FROM events
    WHERE name IN (:signup, :project_created)
      AND occurred_at >= now() - make_interval(days => :days)
    GROUP BY account_id
),
first_export AS (
    SELECT account_id, min(occurred_at) AS exported
    FROM events
    WHERE name = :export_completed
      AND occurred_at >= now() - make_interval(days => :days)
    GROUP BY account_id
)
SELECT
    count(*)                                                          AS accounts,
    (percentile_cont(0.5) WITHIN GROUP (
        ORDER BY extract(epoch FROM exported - started)))::numeric    AS median_seconds,
    (percentile_cont(0.9) WITHIN GROUP (
        ORDER BY extract(epoch FROM exported - started)))::numeric    AS p90_seconds,
    min(extract(epoch FROM exported - started))::numeric              AS fastest_seconds
FROM first_signup JOIN first_export USING (account_id)
WHERE exported >= started
"""

CLEAN_EXPORT_SQL = """
-- A run is "clean" if it was exported and no regeneration was requested
-- against it. The target is 60%: the product's claim is that the review gate
-- makes the first output good enough to hand in.
WITH exported AS (
    SELECT DISTINCT run_id
    FROM events
    WHERE name = :export_completed
      AND run_id IS NOT NULL
      AND occurred_at >= now() - make_interval(days => :days)
),
regenerated AS (
    SELECT DISTINCT COALESCE(payload->>'parentRunId', run_id) AS run_id
    FROM events
    WHERE name = :regeneration_requested
      AND occurred_at >= now() - make_interval(days => :days)
)
SELECT
    count(*)                                                       AS exported_runs,
    count(*) FILTER (WHERE r.run_id IS NULL)                       AS clean_runs,
    CASE WHEN count(*) > 0
         THEN round(100.0 * count(*) FILTER (WHERE r.run_id IS NULL) / count(*), 1)
         ELSE NULL END                                             AS clean_pct
FROM exported e LEFT JOIN regenerated r USING (run_id)
"""

DIAGRAM_FAILURE_SQL = """
SELECT
    a.diagram_type,
    count(*)                                                        AS attempts,
    count(*) FILTER (WHERE a.status = 'failed')                     AS failed,
    count(*) FILTER (WHERE a.status = 'skipped')                    AS skipped,
    round(100.0 * count(*) FILTER (WHERE a.status = 'failed') / count(*), 1) AS failure_pct
FROM generation_artefacts a
JOIN generation_runs r ON r.id = a.run_id
WHERE r.created_at >= now() - make_interval(days => :days)
GROUP BY a.diagram_type
ORDER BY failure_pct DESC, a.diagram_type
"""

RUN_COST_SQL = """
SELECT
    count(*)                                                          AS runs,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms))::numeric  AS median_duration_ms,
    (percentile_cont(0.9) WITHIN GROUP (ORDER BY duration_ms))::numeric  AS p90_duration_ms,
    (percentile_cont(0.5) WITHIN GROUP (
        ORDER BY COALESCE(NULLIF(llm_cost_usd, ''), '0')::numeric))::numeric AS median_cost,
    round(sum(COALESCE(NULLIF(llm_cost_usd, ''), '0')::numeric), 4)   AS total_cost
FROM generation_runs
WHERE status = 'succeeded'
  AND created_at >= now() - make_interval(days => :days)
"""

REVIEW_SQL = """
-- The most important number in the product, split three ways so that
-- "confirmed without editing" cannot be read as good news by default.
SELECT
    payload->>'verdict'                                        AS verdict,
    count(*)                                                   AS confirmations,
    (percentile_cont(0.5) WITHIN GROUP (
        ORDER BY (payload->>'activeSeconds')::numeric))::numeric AS median_active_seconds,
    (percentile_cont(0.5) WITHIN GROUP (
        ORDER BY (payload->>'coverage')::numeric))::numeric     AS median_coverage,
    (percentile_cont(0.5) WITHIN GROUP (
        ORDER BY (payload->>'itemsTotal')::numeric))::numeric   AS median_items
FROM events
WHERE name = :cpm_confirmed
  AND occurred_at >= now() - make_interval(days => :days)
GROUP BY 1
ORDER BY confirmations DESC
"""

EDIT_DISTRIBUTION_SQL = """
SELECT
    LEAST((payload->>'editsTotal')::int, 10)                   AS edits,
    count(*)                                                   AS confirmations,
    count(*) FILTER (WHERE payload->>'verdict' = 'verified')   AS verified,
    count(*) FILTER (WHERE payload->>'verdict' = 'rubber_stamped') AS rubber_stamped
FROM events
WHERE name = :cpm_confirmed
  AND occurred_at >= now() - make_interval(days => :days)
GROUP BY 1
ORDER BY 1
"""


def _rows(result) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings()]


async def collect(days: int = 30, session_factory=SessionFactory) -> Metrics:
    params = {
        "days": days,
        "names": list(FUNNEL),
        "signup": SIGNUP,
        "project_created": PROJECT_CREATED,
        "cpm_confirmed": CPM_CONFIRMED,
        "run_started": RUN_STARTED,
        "export_completed": EXPORT_COMPLETED,
        "regeneration_requested": "regeneration_requested",
    }

    async with session_factory() as session:
        counts = {
            row["name"]: row["accounts"]
            for row in _rows(await session.execute(text(FUNNEL_SQL), params))
        }
        timing = _rows(await session.execute(text(TIME_TO_FIRST_EXPORT_SQL), params))
        clean = _rows(await session.execute(text(CLEAN_EXPORT_SQL), params))
        failures = _rows(await session.execute(text(DIAGRAM_FAILURE_SQL), params))
        cost = _rows(await session.execute(text(RUN_COST_SQL), params))
        review = _rows(await session.execute(text(REVIEW_SQL), params))
        edits = _rows(await session.execute(text(EDIT_DISTRIBUTION_SQL), params))

    steps: list[FunnelStep] = []
    start = counts.get(FUNNEL[0]) or counts.get(FUNNEL[1]) or 0
    previous: int | None = None
    for name in FUNNEL:
        reached = counts.get(name, 0)
        steps.append(
            FunnelStep(
                name=name,
                accounts=reached,
                from_previous_pct=(round(100 * reached / previous, 1) if previous else None),
                from_start_pct=round(100 * reached / start, 1) if start else None,
                dropped=max((previous or 0) - reached, 0) if previous is not None else 0,
            )
        )
        previous = reached

    verdicts = {row["verdict"]: row for row in review}
    total_confirms = sum(row["confirmations"] for row in review) or 0
    return Metrics(
        days=days,
        funnel=steps,
        time_to_first_export=timing[0] if timing else {},
        clean_export_rate=clean[0] if clean else {},
        diagram_failures=failures,
        run_cost=cost[0] if cost else {},
        review={
            "total": total_confirms,
            "buckets": [
                {
                    "verdict": verdict,
                    "confirmations": verdicts.get(verdict, {}).get("confirmations", 0),
                    "share_pct": (
                        round(
                            100
                            * verdicts.get(verdict, {}).get("confirmations", 0)
                            / total_confirms,
                            1,
                        )
                        if total_confirms
                        else None
                    ),
                    "median_active_seconds": verdicts.get(verdict, {}).get("median_active_seconds"),
                    "median_coverage": verdicts.get(verdict, {}).get("median_coverage"),
                    "meaning": interpret(verdict),
                }
                for verdict in (EDITED, VERIFIED, RUBBER_STAMPED, UNKNOWN)
            ],
        },
        edit_distribution=edits,
    )


def as_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))
