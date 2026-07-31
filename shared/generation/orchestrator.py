"""Executing a persisted generation run.

This is what the worker calls. It owns the database side of a run — status
transitions, per-artefact rows, duration and cost — and delegates the actual
work to `execute_generation_run`, so render-then-validate exists in exactly one
place and the FR-10 check cannot be forgotten on this path.

Idempotency (NFR-R3) has two halves:

* A run that already **succeeded** is not re-executed. Re-running it would burn
  time and, more importantly, rewrite artefacts a user may already be looking at.
* A run that was interrupted **is** re-executed, and its artefacts are upserted
  against a unique key. A worker that died mid-run, an arq retry, or two
  workers racing the same job all converge on one row per (run, type, format)
  rather than a pile of duplicates. Deterministic mappers make the overwrite
  byte-identical.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from consistency.validator import ConsistencyViolation
from cpm.schema import CPM
from diagrams.renderer import DiagramRenderer
from diagrams.types import DiagramResult, RenderFormat, SkippedDiagram
from generation.run import execute_generation_run
from llm.telemetry import RecordingSink
from store.models import (
    ArtefactStatus,
    CPMVersionRow,
    GenerationArtefactRow,
    GenerationRunRow,
    RunStatus,
)
from store.session import SessionFactory

logger = logging.getLogger(__name__)


class RunNotFound(LookupError):
    pass


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    status: str
    duration_ms: int
    succeeded: int
    failed: int
    skipped: int
    llm_cost_usd: str | None
    error: str | None = None


def artefact_id(run_id: str, diagram_type: str, fmt: str) -> str:
    return f"{run_id}:{diagram_type}:{fmt}"


def status_of(result: DiagramResult) -> str:
    if isinstance(result, SkippedDiagram):
        return ArtefactStatus.SKIPPED
    return ArtefactStatus.SUCCEEDED if result.ok else ArtefactStatus.FAILED


def artefact_values(
    run_id: str,
    fmt: str,
    result: DiagramResult,
    cpm_version_id: str,
    origin_run_id: str,
) -> dict:
    """One rendered result as a row. Shared with regeneration so both paths
    record provenance the same way."""
    return {
        "id": artefact_id(run_id, result.diagram_type, fmt),
        "run_id": run_id,
        "diagram_type": result.diagram_type,
        "format": fmt,
        "status": status_of(result),
        "title": result.title,
        "engine": getattr(result, "engine", None),
        "source": getattr(result, "source", None) or None,
        "content": getattr(result, "content", None),
        "error": getattr(result, "error", None) or getattr(result, "reason", None),
        "attempts": getattr(result, "attempts", 0),
        "cpm_version_id": cpm_version_id,
        "origin_run_id": origin_run_id,
    }


async def upsert_artefact(session, run_id: str, fmt: str, values: dict) -> None:
    """Insert or overwrite one artefact row.

    ON CONFLICT against uq_run_artefact is what makes a retry safe. Without it
    a re-run would append a second copy of every diagram and the user would
    receive eight figures twice.
    """
    statement = insert(GenerationArtefactRow).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_run_artefact",
            set_={
                key: statement.excluded[key]
                for key in values
                if key not in {"id", "run_id", "diagram_type", "format"}
            },
        )
    )


async def finalise_run(
    run_id: str,
    status: str,
    error: str | None,
    started: datetime,
    sink: RecordingSink | None,
    session_factory,
) -> tuple[int, Decimal | None]:
    """Close out a run: status, duration, cost. Shared by both run kinds.

    `sink` may be None for a path that cannot make model calls at all, which
    still records a measured zero rather than an absent number.
    """
    completed = datetime.now(UTC)
    duration_ms = int((completed - started).total_seconds() * 1000)

    sink = sink or RecordingSink()
    total_cost = sink.total_cost_usd

    async with session_factory() as session:
        run = await session.get(GenerationRunRow, run_id)
        run.status = status
        run.error = error
        run.completed_at = completed
        run.duration_ms = duration_ms
        # A run with no model calls costs exactly zero, which is a measurement
        # rather than a gap — C-3 keeps the LLM out of the render path.
        run.llm_cost_usd = None if total_cost is None else str(Decimal(total_cost))
        run.llm_input_tokens = sum(record.input_tokens for record in sink.records)
        run.llm_output_tokens = sum(record.output_tokens for record in sink.records)
        await session.commit()

    return duration_ms, total_cost


async def execute_run(
    run_id: str,
    renderer: DiagramRenderer,
    session_factory=SessionFactory,
    cost_sink: RecordingSink | None = None,
) -> RunOutcome:
    started = datetime.now(UTC)
    sink = cost_sink or RecordingSink()

    async with session_factory() as session:
        run = await session.get(GenerationRunRow, run_id)
        if run is None:
            raise RunNotFound(f"no generation run {run_id!r}")

        if run.status == RunStatus.SUCCEEDED:
            # Already done. Re-rendering would rewrite artefacts a user may be
            # looking at, for no gain — the mappers are deterministic.
            logger.info("run %s already succeeded; nothing to do", run_id)
            return RunOutcome(
                run_id=run_id,
                status=run.status,
                duration_ms=run.duration_ms or 0,
                succeeded=0,
                failed=0,
                skipped=0,
                llm_cost_usd=run.llm_cost_usd,
            )

        version = await session.get(CPMVersionRow, run.cpm_version_id)
        if version is None:
            raise RunNotFound(f"run {run_id!r} references missing CPM version")

        cpm = CPM.model_validate(version.payload)
        requested = list(run.requested_types)
        fmt = RenderFormat(run.fmt)

        run.status = RunStatus.RUNNING
        run.started_at = started
        run.attempts += 1
        run.error = None

        version_id = run.cpm_version_id
        for diagram_type in requested:
            await upsert_artefact(
                session,
                run_id,
                fmt.value,
                {
                    "id": artefact_id(run_id, diagram_type, fmt.value),
                    "run_id": run_id,
                    "diagram_type": diagram_type,
                    "format": fmt.value,
                    "status": ArtefactStatus.RUNNING,
                    "error": None,
                    "cpm_version_id": version_id,
                    "origin_run_id": run_id,
                },
            )
        await session.commit()

    async def persist(result: DiagramResult) -> None:
        # Each diagram lands as it finishes, so the client sees progress rather
        # than a single jump at the end.
        async with session_factory() as progress_session:
            await upsert_artefact(
                progress_session,
                run_id,
                fmt.value,
                artefact_values(run_id, fmt.value, result, version_id, run_id),
            )
            await progress_session.commit()

    status = RunStatus.SUCCEEDED
    error: str | None = None
    counts = {"succeeded": 0, "failed": 0, "skipped": 0}

    try:
        result = await execute_generation_run(cpm, renderer, requested, fmt, on_result=persist)
    except ConsistencyViolation as exc:
        # FR-10 is a hard gate: the diagrams disagree with the model, so the
        # run failed even though every render succeeded.
        status = RunStatus.FAILED
        error = str(exc)
        logger.error("run %s failed consistency validation", run_id)
    except Exception as exc:
        status = RunStatus.FAILED
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("run %s failed", run_id)
    else:
        counts = {
            "succeeded": len(result.rendered),
            "failed": len(result.failed),
            "skipped": len(result.skipped),
        }

    duration_ms, total_cost = await finalise_run(
        run_id, status, error, started, sink, session_factory
    )

    return RunOutcome(
        run_id=run_id,
        status=status,
        duration_ms=duration_ms,
        succeeded=counts["succeeded"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        llm_cost_usd=None if total_cost is None else str(total_cost),
        error=error,
    )


async def artefacts_of(run_id: str, session_factory=SessionFactory) -> list[GenerationArtefactRow]:
    async with session_factory() as session:
        rows = await session.scalars(
            select(GenerationArtefactRow)
            .where(GenerationArtefactRow.run_id == run_id)
            .order_by(GenerationArtefactRow.diagram_type)
        )
        return list(rows)
