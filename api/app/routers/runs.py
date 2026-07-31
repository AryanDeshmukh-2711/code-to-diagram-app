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

from arq import create_pool
from arq.connections import RedisSettings
from diagrams.registry import registered_types
from diagrams.types import RenderFormat
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
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


class RunOut(BaseModel):
    runId: str
    projectId: str
    cpmVersionId: str
    status: str
    requestedTypes: list[str]
    artefacts: list[ArtefactOut]
    durationMs: int | None = None
    llmCostUsd: str | None = None
    attempts: int = 0
    error: str | None = None


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
            )
            for row in rows
        ],
    )


@router.post("", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: StartRunIn) -> RunOut:
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
            requested_types=sorted(wanted),
            fmt=fmt.value,
            status=RunStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        session.add(run)
        await session.commit()
        snapshot = await _snapshot(session, run)

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job("render_run", run.id, _job_id=f"render:{run.id}")
    finally:
        await pool.aclose()

    return snapshot


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str) -> RunOut:
    async with SessionFactory() as session:
        run = await session.get(GenerationRunRow, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no run {run_id!r}")
        return await _snapshot(session, run)


@router.get("/{run_id}/events")
async def stream_run(run_id: str) -> StreamingResponse:
    """Server-sent events, one per change of run state (SRS §4.3)."""

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
