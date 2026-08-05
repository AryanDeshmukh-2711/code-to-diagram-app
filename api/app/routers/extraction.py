"""Turning a description or a PDF into a CPM draft, over HTTP.

The request does two kinds of work, and only one of them is allowed to be
slow. Validating an upload — its size, its page count, whether it parses as a
PDF at all — is cheap and synchronous, so it happens here and gives a specific
reason immediately. Anything that touches the model, or walks every page of a
PDF extracting text, happens in the worker (C-4): the row is written, the job
is queued, and the request returns in milliseconds regardless of how long
extraction takes.

The FR-5 floor is not a failure mode this endpoint has any opinion about. A
description that does not support a model produces a *succeeded* extraction
carrying the service's own guidance — the same honest outcome
`ExtractionService` has always returned, now visible over HTTP.
"""

import asyncio
import json
import uuid
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from extraction.pdf_text import PdfRejected, probe_pdf
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from store.models import ExtractionRow
from store.session import SessionFactory

from app.core.config import get_settings
from app.core.identity import get_or_404
from app.core.projects import ensure_project

router = APIRouter(prefix="/projects/{project_id}", tags=["extraction"])

POLL_SECONDS = 0.4
"""Matches the run-progress stream: extraction is a single-digit-second job,
not one that needs finer polling."""


class ExtractionOut(BaseModel):
    extractionId: str
    projectId: str
    status: str
    outcome: str | None = None
    reason: str | None = None
    guidance: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    wordCount: int | None = None
    entitiesFound: int | None = None
    relationshipsFound: int | None = None
    cpmDraftReady: bool = False
    error: str | None = None


def _snapshot(row: ExtractionRow) -> ExtractionOut:
    return ExtractionOut(
        extractionId=row.id,
        projectId=row.project_id,
        status=row.status,
        outcome=row.outcome,
        reason=row.reason,
        guidance=list(row.guidance or []),
        notes=list(row.notes or []),
        wordCount=row.word_count,
        entitiesFound=row.entities_found,
        relationshipsFound=row.relationships_found,
        cpmDraftReady=row.cpm_draft_ready,
        error=row.error,
    )


@router.post("/extract", response_model=ExtractionOut, status_code=status.HTTP_202_ACCEPTED)
async def start_extraction(
    project_id: str,
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),  # noqa: B008 -- FastAPI's DI marker, not a mutable default
    projectName: str = Form(default=""),
    previousExtractionId: str | None = Form(default=None),
) -> ExtractionOut:
    """Queue an extraction from pasted text or an uploaded PDF. 202; nothing
    is rendered or sent to a model here (C-4).

    `previousExtractionId` is how a chat reply to an FR-5 "insufficient
    input" outcome keeps going: `text` becomes the detail the user just
    added, combined here with whatever the earlier attempt already had —
    a pasted description or a PDF's extracted text, either one sits in that
    row's own `source_text` — rather than the user having to retype or
    re-upload everything from scratch. Still exactly one model call per
    attempt (C-1); a second attempt is a new attempt, not a second call
    layered onto the first.
    """
    if previousExtractionId:
        if not text or not text.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="continuing an extraction needs the additional detail as text",
            )
        async with SessionFactory() as session:
            previous = await get_or_404(session, ExtractionRow, previousExtractionId, "extraction")
        if previous.project_id != project_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"extraction {previousExtractionId!r} does not belong to project {project_id!r}"
                ),
            )
        combined_text = (
            f"{previous.source_text}\n\n{text.strip()}" if previous.source_text else text.strip()
        )
        pdf_bytes = None
    else:
        if bool(text and text.strip()) == bool(file is not None):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="send exactly one of: text, or a PDF file",
            )

        pdf_bytes = None
        if file is not None:
            if file.content_type not in ("application/pdf", "application/x-pdf") and not (
                file.filename or ""
            ).lower().endswith(".pdf"):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"expected a PDF, got {file.content_type or 'an unknown file type'}",
                )
            pdf_bytes = await file.read()
            try:
                probe_pdf(pdf_bytes)
            except PdfRejected as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
        combined_text = text

    async with SessionFactory() as session:
        await ensure_project(session, project_id, projectName or project_id)

        row = ExtractionRow(
            id=f"ext_{uuid.uuid4().hex[:16]}",
            project_id=project_id,
            input_kind="pdf" if pdf_bytes is not None else "text",
            project_name=projectName.strip() or None,
            source_text=combined_text,
            source_pdf=pdf_bytes,
            status="pending",
        )
        session.add(row)
        await session.commit()
        extraction_id = row.id

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job(
            "extract_cpm",
            extraction_id,
            _job_id=f"extract:{extraction_id}",
            _queue_name="arq:default",
        )
    finally:
        await pool.aclose()

    return ExtractionOut(extractionId=extraction_id, projectId=project_id, status="pending")


@router.get("/extractions/{extraction_id}", response_model=ExtractionOut)
async def get_extraction(project_id: str, extraction_id: str) -> ExtractionOut:
    async with SessionFactory() as session:
        row = await get_or_404(session, ExtractionRow, extraction_id, "extraction")
        return _snapshot(row)


@router.get("/extractions/{extraction_id}/events")
async def stream_extraction(project_id: str, extraction_id: str) -> StreamingResponse:
    """Server-sent progress, the same shape run progress already streams."""
    async with SessionFactory() as session:
        await get_or_404(session, ExtractionRow, extraction_id, "extraction")

    async def events_stream():
        previous: str | None = None
        while True:
            async with SessionFactory() as session:
                row = await session.get(ExtractionRow, extraction_id)
                if row is None:
                    yield _sse({"error": f"no extraction {extraction_id!r}"})
                    return
                payload: dict[str, Any] = _snapshot(row).model_dump()

            encoded = json.dumps(payload, sort_keys=True)
            if encoded != previous:
                previous = encoded
                yield _sse(payload)

            if row.status in ("succeeded", "failed"):
                return
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(
        events_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
