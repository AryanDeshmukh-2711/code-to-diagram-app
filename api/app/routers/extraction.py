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
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from store.models import ExtractionRow
from store.session import SessionFactory

from app.core.config import get_settings
from app.core.identity import owned_extraction, require_account
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
    account: str = Depends(require_account),
) -> ExtractionOut:
    """Queue an extraction from pasted text or an uploaded PDF. 202; nothing
    is rendered or sent to a model here (C-4)."""
    if bool(text and text.strip()) == bool(file is not None):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="send exactly one of: text, or a PDF file",
        )

    pdf_bytes: bytes | None = None
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

    async with SessionFactory() as session:
        # A project created by dropping a PDF counts against the free tier
        # exactly as one created by seeding a draft does (FR-22).
        await ensure_project(session, project_id, account, projectName or project_id)

        row = ExtractionRow(
            id=f"ext_{uuid.uuid4().hex[:16]}",
            project_id=project_id,
            account_id=account,
            input_kind="pdf" if pdf_bytes is not None else "text",
            project_name=projectName.strip() or None,
            source_text=text,
            source_pdf=pdf_bytes,
            status="pending",
        )
        session.add(row)
        await session.commit()
        extraction_id = row.id

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        # No tier concept for extraction: it always runs on the default pool,
        # same as regenerate_diagram. Leaving _queue_name unset lands the job
        # on arq's own default queue, which no worker here consumes.
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
async def get_extraction(
    project_id: str, extraction_id: str, account: str = Depends(require_account)
) -> ExtractionOut:
    async with SessionFactory() as session:
        row = await owned_extraction(session, extraction_id, account)
        return _snapshot(row)


@router.get("/extractions/{extraction_id}/events")
async def stream_extraction(
    project_id: str, extraction_id: str, account: str = Depends(require_account)
) -> StreamingResponse:
    """Server-sent progress, the same shape run progress already streams."""
    async with SessionFactory() as session:
        await owned_extraction(session, extraction_id, account)

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
