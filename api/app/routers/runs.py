"""Generation runs over HTTP.

The request path never renders (C-4). POST creates the run row and enqueues a
job; everything after that happens in the worker pool. The endpoint returns in
milliseconds regardless of how long the run takes.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from analytics import events
from arq import create_pool
from arq.connections import RedisSettings
from billing.quota import QuotaExceeded, check_new_run, check_template
from diagrams.registry import registered_types
from diagrams.types import RenderFormat
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from generation.orchestrator import RunNotFound
from generation.regenerate import (
    NotRegenerable,
    create_regeneration_run,
    lineage,
    plan_regeneration,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from store.models import (
    CPMVersionRow,
    GenerationArtefactRow,
    GenerationRunRow,
    RunStatus,
)
from store.session import SessionFactory

from app.core.config import get_settings
from app.core.identity import owned_project, owned_run, require_account
from app.core.quota import as_http

router = APIRouter(prefix="/runs", tags=["generation"])

POLL_SECONDS = 0.4
"""How often the progress stream re-reads run state. Renders take well under a
second each, so anything finer just burns queries."""


class StartRunIn(BaseModel):
    projectId: str
    cpmVersionId: str
    diagramTypes: list[str] = Field(default_factory=list)
    templateId: str | None = None
    format: str = "svg"


class ArtefactOut(BaseModel):
    diagramType: str
    title: str
    status: str
    engine: str | None = None
    error: str | None = None
    attempts: int = 0
    bytes: int | None = None
    cpmVersionId: str | None = None
    originRunId: str | None = None
    carriedForward: bool = False
    """True when this figure was drawn by an earlier run. The whole point of
    FR-12 is that most of the set is untouched, and the artefact list should
    show that rather than implying eight fresh renders."""


class RunOut(BaseModel):
    runId: str
    projectId: str
    cpmVersionId: str
    status: str
    tier: str | None = None
    kind: str = "full"
    parentRunId: str | None = None
    requestedTypes: list[str]
    artefacts: list[ArtefactOut]
    durationMs: int | None = None
    llmCostUsd: str | None = None
    attempts: int = 0
    error: str | None = None


class RegenerateIn(BaseModel):
    diagramType: str
    cpmVersionId: str | None = None
    """Defaults to the run's own version. Naming a newer confirmed version is
    the "I edited the model" case; either way it is a version a human already
    confirmed, never a fresh extraction."""


class RegenerateOut(BaseModel):
    changed: bool
    reason: str
    diagramType: str
    cpmVersionId: str
    runId: str | None = None
    previousStatus: str | None = None
    staleTypes: list[str] = Field(default_factory=list)


class LineageEntry(BaseModel):
    runId: str
    kind: str
    status: str
    regenerated: list[str]
    cpmVersionId: str
    createdAt: str | None = None
    completedAt: str | None = None


async def _snapshot(session, run: GenerationRunRow) -> RunOut:
    rows = await session.scalars(
        select(GenerationArtefactRow)
        .where(GenerationArtefactRow.run_id == run.id)
        .order_by(GenerationArtefactRow.diagram_type)
    )
    return RunOut(
        runId=run.id,
        projectId=run.project_id,
        cpmVersionId=run.cpm_version_id,
        status=run.status,
        tier=run.tier,
        kind=run.kind,
        parentRunId=run.parent_run_id,
        requestedTypes=list(run.requested_types),
        durationMs=run.duration_ms,
        llmCostUsd=run.llm_cost_usd,
        attempts=run.attempts,
        error=run.error,
        artefacts=[
            ArtefactOut(
                diagramType=row.diagram_type,
                title=row.title,
                status=row.status,
                engine=row.engine,
                error=row.error,
                attempts=row.attempts,
                bytes=len(row.content) if row.content else None,
                cpmVersionId=row.cpm_version_id,
                originRunId=row.origin_run_id,
                carriedForward=bool(row.origin_run_id and row.origin_run_id != run.id),
            )
            for row in rows
        ],
    )


@router.post("", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: StartRunIn, account: str = Depends(require_account)) -> RunOut:
    """Queue a run. Returns 202 immediately — nothing is rendered here."""
    wanted = body.diagramTypes or registered_types()
    unknown = sorted(set(wanted) - set(registered_types()))
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"unknown diagram types: {', '.join(unknown)}",
        )
    try:
        fmt = RenderFormat(body.format)
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"unsupported format {body.format!r}"
        ) from None

    async with SessionFactory() as session:
        # You may only generate from your own project (NFR-S2).
        project = await owned_project(session, body.projectId, account)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no project {body.projectId!r}")

        # Entitlements first, before a job is queued or a row is written. A
        # tier that cannot render SVG must be refused here rather than have the
        # worker produce artefacts nobody is allowed to download.
        try:
            tier = await check_new_run(session, account, fmt.value)
            if body.templateId:
                await check_template(session, account, body.templateId)
        except QuotaExceeded as exc:
            raise as_http(exc) from None

        version = await session.get(CPMVersionRow, body.cpmVersionId)
        if version is None:
            # FR-6: generation runs from a confirmed version, and there is no
            # way to ask for one that does not exist.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"no confirmed CPM version {body.cpmVersionId!r}",
            )

        run = GenerationRunRow(
            id=f"run_{uuid.uuid4().hex[:16]}",
            project_id=body.projectId,
            cpm_version_id=body.cpmVersionId,
            template_id=body.templateId,
            account_id=account,
            tier=tier.id,
            requested_types=sorted(wanted),
            fmt=fmt.value,
            status=RunStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        session.add(run)
        await events.record(
            session,
            events.RUN_STARTED,
            account_id=account,
            project_id=body.projectId,
            run_id=run.id,
            tier=tier.id,
            payload={
                "diagramTypes": sorted(wanted),
                "format": fmt.value,
                "templateId": body.templateId,
                "kind": "full",
            },
        )
        await session.commit()
        snapshot = await _snapshot(session, run)

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        # Priority tiers land on their own queue, which a second worker pool
        # consumes. One queue with a "priority" flag would still be FIFO.
        await pool.enqueue_job(
            "render_run",
            run.id,
            _job_id=f"render:{run.id}",
            _queue_name=f"arq:{tier.queue}",
        )
    finally:
        await pool.aclose()

    return snapshot


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, account: str = Depends(require_account)) -> RunOut:
    async with SessionFactory() as session:
        run = await owned_run(session, run_id, account)
        return await _snapshot(session, run)


@router.post("/{run_id}/regenerate", response_model=RegenerateOut)
async def regenerate(
    run_id: str,
    body: RegenerateIn,
    response: Response,
    account: str = Depends(require_account),
) -> RegenerateOut:
    """FR-12: redraw one diagram from an already-confirmed model.

    Answers synchronously when there is nothing to do, and only then. Deciding
    costs one mapper call — a pure function over a CPM already in hand, no
    network, well under a millisecond — so telling the user "your model has not
    changed" does not need a job, a queue or a spinner. Everything that renders
    still runs in the worker (C-4).
    """
    async with SessionFactory() as session:
        await owned_run(session, run_id, account)

    try:
        plan = await plan_regeneration(run_id, body.diagramType, body.cpmVersionId)
    except RunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except NotRegenerable as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except KeyError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"unknown diagram type: {exc}"
        ) from None

    out = RegenerateOut(
        changed=plan.changed,
        reason=plan.reason,
        diagramType=plan.diagram_type,
        cpmVersionId=plan.cpm_version_id,
        previousStatus=plan.previous_status,
        staleTypes=plan.stale_types,
    )
    if not plan.changed:
        # 200, not 202: nothing was accepted for processing, and no run row is
        # written. A history of non-events would make the history useless.
        response.status_code = status.HTTP_200_OK
        return out

    child_id = await create_regeneration_run(plan, template_id=None)
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job("regenerate_diagram", child_id, _job_id=f"regen:{child_id}")
    finally:
        await pool.aclose()

    async with SessionFactory() as session:
        parent = await session.get(GenerationRunRow, run_id)
        await events.record(
            session,
            "regeneration_requested",
            account_id=parent.account_id if parent else None,
            project_id=plan.project_id,
            run_id=child_id,
            tier=parent.tier if parent else None,
            payload={
                "parentRunId": run_id,
                "diagramType": plan.diagram_type,
                "reason": plan.reason,
                "staleTypes": plan.stale_types,
            },
        )
        await session.commit()

    out.runId = child_id
    response.status_code = status.HTTP_202_ACCEPTED
    return out


@router.get("/{run_id}/history", response_model=list[LineageEntry])
async def history(run_id: str, account: str = Depends(require_account)) -> list[LineageEntry]:
    """What was regenerated, and when — oldest first."""
    async with SessionFactory() as session:
        await owned_run(session, run_id, account)
    chain = await lineage(run_id)
    if not chain:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no run {run_id!r}")
    return [
        LineageEntry(
            runId=run.id,
            kind=run.kind,
            status=run.status,
            regenerated=list(run.requested_types),
            cpmVersionId=run.cpm_version_id,
            createdAt=run.created_at.isoformat() if run.created_at else None,
            completedAt=run.completed_at.isoformat() if run.completed_at else None,
        )
        for run in chain
    ]


@router.get("/{run_id}/events")
async def stream_run(run_id: str, account: str = Depends(require_account)) -> StreamingResponse:
    """Server-sent events, one per change of run state (SRS §4.3)."""

    async with SessionFactory() as session:
        # Checked once, before the stream opens: an unowned run must not
        # leak progress either.
        await owned_run(session, run_id, account)

    async def events():
        previous: str | None = None
        while True:
            async with SessionFactory() as session:
                run = await session.get(GenerationRunRow, run_id)
                if run is None:
                    yield _sse({"error": f"no run {run_id!r}"})
                    return
                snapshot = await _snapshot(session, run)

            payload: dict[str, Any] = snapshot.model_dump()
            encoded = json.dumps(payload, sort_keys=True)
            # Only emit on change: a client watching a 0.8s run should not
            # receive twenty identical frames.
            if encoded != previous:
                previous = encoded
                yield _sse(payload)

            if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED):
                return
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
