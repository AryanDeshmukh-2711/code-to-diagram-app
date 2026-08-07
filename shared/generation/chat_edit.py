"""Executing a chat edit-intent request. The worker's half of C-4.

The API's half writes a `ChatEditRow` and enqueues; this is what actually
calls the model. `ChatEditService` does the parsing; this module's job is to
feed it the project's current draft, and then — if and only if parsing named
one clear op — apply it through `apply_edit_op`, the exact function
`POST .../review/edit` calls. No second implementation of what an edit means
exists here (C-3).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from analytics import events
from chat import ChatEditService, Clarify, NotAnEdit, ParsedEdit
from cpm.schema import CPMDraft
from llm.gateway import build_default_gateway
from review import ReviewError, apply_edit_op
from store.models import ChatEditRow, CPMDraftRow
from store.session import SessionFactory

logger = logging.getLogger(__name__)


class ChatEditNotFound(LookupError):
    pass


@dataclass(frozen=True)
class ChatEditOutcome:
    edit_id: str
    status: str
    outcome: str | None
    duration_ms: int
    error: str | None = None


async def run_chat_edit(
    edit_id: str,
    session_factory=SessionFactory,
    service: ChatEditService | None = None,
    api_key_override: str | None = None,
) -> ChatEditOutcome:
    started = datetime.now(UTC)

    async with session_factory() as session:
        row = await session.get(ChatEditRow, edit_id)
        if row is None:
            raise ChatEditNotFound(f"no chat edit {edit_id!r}")
        if row.status == "succeeded":
            # Idempotent, like every other job: a retry must not re-parse a
            # message that already produced a result the user has seen.
            return ChatEditOutcome(
                edit_id=edit_id,
                status=row.status,
                outcome=row.outcome,
                duration_ms=row.duration_ms or 0,
            )

        project_id = row.project_id
        account_id = row.account_id
        message = row.message

        row.status = "running"
        await session.commit()

        draft_row = await session.get(CPMDraftRow, project_id)

    status = "succeeded"
    error: str | None = None
    draft: CPMDraft | None = None
    parsed = None

    try:
        if draft_row is None:
            raise ValueError(f"no model is being reviewed for project {project_id!r}")
        draft = CPMDraft.model_validate(draft_row.payload)
        chat_service = service or ChatEditService(
            build_default_gateway(api_key_override=api_key_override)
        )
        parsed = await chat_service.parse(message, draft, user_id=account_id)
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("chat edit %s failed to parse", edit_id)

    outcome: str | None = None
    applied_op: str | None = None
    summary: str | None = None
    references_updated: int | None = None
    clarify_question: str | None = None
    reason: str | None = None

    if isinstance(parsed, NotAnEdit):
        outcome = "not_edit"
    elif isinstance(parsed, Clarify):
        outcome = "clarify"
        clarify_question = parsed.question
    elif isinstance(parsed, ParsedEdit):
        assert draft is not None
        try:
            result = apply_edit_op(draft, parsed.edit)
        except ReviewError as exc:
            # Same as a malformed HTTP request to review/edit: the parse was
            # structurally fine, the reference it named was not (C-3).
            outcome = "rejected"
            reason = str(exc)
        else:
            outcome = "applied"
            applied_op = parsed.edit.op
            summary = result.summary
            references_updated = result.references_updated
            async with session_factory() as session:
                fresh = await session.get(CPMDraftRow, project_id)
                fresh.payload = result.draft.model_dump(by_alias=True, mode="json")
                await events.record(
                    session,
                    events.CHAT_EDIT_APPLIED,
                    account_id=account_id,
                    project_id=project_id,
                    payload={"message": message, "op": applied_op, "editId": edit_id},
                )
                await session.commit()

    completed = datetime.now(UTC)
    duration_ms = int((completed - started).total_seconds() * 1000)

    async with session_factory() as session:
        row = await session.get(ChatEditRow, edit_id)
        row.status = status
        row.outcome = outcome
        row.applied_op = applied_op
        row.summary = summary
        row.references_updated = references_updated
        row.clarify_question = clarify_question
        row.reason = reason
        row.error = error
        row.duration_ms = duration_ms
        row.completed_at = completed
        await session.commit()

    return ChatEditOutcome(
        edit_id=edit_id,
        status=status,
        outcome=outcome,
        duration_ms=duration_ms,
        error=error,
    )
