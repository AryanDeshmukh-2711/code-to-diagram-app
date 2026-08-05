"""Turning one chat message into a candidate edit, over HTTP.

The request only ever writes a row and queues a job — parsing calls the model,
and the model never runs in the request cycle (C-4). What comes back is one of
three honest outcomes: an applied edit, a clarifying question, or "that wasn't
an edit" — never a guess applied silently. The actual mutation, when there is
one, happens through the exact function `POST .../review/edit` calls; this
endpoint never touches a CPMDraft directly (C-3).
"""

import asyncio
import json
import uuid
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from store.models import ChatEditRow, CPMDraftRow, ProjectRow
from store.session import SessionFactory

from app.core.config import get_settings
from app.core.identity import get_or_404

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])

POLL_SECONDS = 0.4
"""Matches extraction's stream: a single chat parse is a single-digit-second
to low-double-digit-second job, not one that needs finer polling."""


class ChatMessageIn(BaseModel):
    message: str


class ChatEditOut(BaseModel):
    editId: str
    projectId: str
    status: str
    outcome: str | None = None
    appliedOp: str | None = None
    summary: str | None = None
    referencesUpdated: int | None = None
    clarifyQuestion: str | None = None
    reason: str | None = None
    error: str | None = None


def _snapshot(row: ChatEditRow) -> ChatEditOut:
    return ChatEditOut(
        editId=row.id,
        projectId=row.project_id,
        status=row.status,
        outcome=row.outcome,
        appliedOp=row.applied_op,
        summary=row.summary,
        referencesUpdated=row.references_updated,
        clarifyQuestion=row.clarify_question,
        reason=row.reason,
        error=row.error,
    )


@router.post("", response_model=ChatEditOut, status_code=status.HTTP_202_ACCEPTED)
async def send_message(project_id: str, body: ChatMessageIn) -> ChatEditOut:
    """Queue one chat message for parsing. 202; nothing is parsed or applied
    here (C-4)."""
    if not body.message.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="message cannot be empty")

    async with SessionFactory() as session:
        await get_or_404(session, ProjectRow, project_id, "project")
        draft = await session.get(CPMDraftRow, project_id)
        if draft is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"No model is being reviewed for project {project_id!r}.",
            )

        row = ChatEditRow(
            id=f"chat_{uuid.uuid4().hex[:16]}",
            project_id=project_id,
            message=body.message,
            status="pending",
        )
        session.add(row)
        await session.commit()
        edit_id = row.id

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job(
            "parse_chat_edit",
            edit_id,
            _job_id=f"chat_edit:{edit_id}",
            _queue_name="arq:default",
        )
    finally:
        await pool.aclose()

    return ChatEditOut(editId=edit_id, projectId=project_id, status="pending")


@router.get("/{edit_id}", response_model=ChatEditOut)
async def get_chat_edit(project_id: str, edit_id: str) -> ChatEditOut:
    async with SessionFactory() as session:
        row = await get_or_404(session, ChatEditRow, edit_id, "chat edit")
        return _snapshot(row)


@router.get("/{edit_id}/events")
async def stream_chat_edit(project_id: str, edit_id: str) -> StreamingResponse:
    """Server-sent progress, the same shape extraction and run progress
    already stream."""
    async with SessionFactory() as session:
        await get_or_404(session, ChatEditRow, edit_id, "chat edit")

    async def events_stream():
        previous: str | None = None
        while True:
            async with SessionFactory() as session:
                row = await session.get(ChatEditRow, edit_id)
                if row is None:
                    yield _sse({"error": f"no chat edit {edit_id!r}"})
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
