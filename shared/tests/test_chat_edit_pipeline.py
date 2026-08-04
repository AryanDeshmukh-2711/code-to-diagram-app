"""run_chat_edit end to end: a chat message becomes a row, and the row becomes
exactly one of applied / clarify / not_edit / rejected -- never a silent
mutation, and never by any path but `apply_edit_op` (C-3).

This is the DB-backed coverage P-M6-1's equivalent (`run_extraction`) never
got: `service` is injectable the same way `session_factory` already is, so
the whole worker orchestration runs against real Postgres without a live
model.
"""

import json

import pytest
from sqlalchemy import select

from chat import ChatEditService
from cpm.fixtures import library_management_system_payload
from cpm.schema import CPMDraft
from generation.chat_edit import ChatEditNotFound, run_chat_edit
from llm.config import TaskConfig
from llm.gateway import LLMGateway
from llm.providers.scripted import ScriptedProvider
from store.models import ChatEditRow, CPMDraftRow, EventRow

PROJECT_ID = "proj_chat"

TASK = TaskConfig(
    provider="scripted",
    model="stub-model",
    max_tokens=1024,
    temperature=0.0,
    timeout_seconds=30.0,
    system_prompt="Parse one chat message into an edit intent.",
)


def _draft_payload() -> dict:
    return CPMDraft.model_validate(library_management_system_payload()).model_dump(
        by_alias=True, mode="json"
    )


def service_returning(payload: dict) -> ChatEditService:
    gateway = LLMGateway(
        providers={"scripted": ScriptedProvider([json.dumps(payload)])},
        tasks={"chat_edit_intent": TASK},
    )
    return ChatEditService(gateway)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(
            CPMDraftRow(
                project_id=PROJECT_ID,
                project_name="Library Management System",
                payload=_draft_payload(),
            )
        )
        await session.commit()
    return session_factory


async def _seed_edit(session_factory, edit_id: str, message: str) -> None:
    async with session_factory() as session:
        session.add(
            ChatEditRow(
                id=edit_id,
                project_id=PROJECT_ID,
                account_id="acct_test",
                message=message,
                status="pending",
            )
        )
        await session.commit()


async def _run(session_factory, edit_id: str, payload: dict, message: str = "some message"):
    await _seed_edit(session_factory, edit_id, message)
    return await run_chat_edit(
        edit_id, session_factory=session_factory, service=service_returning(payload)
    )


# --------------------------------------------------------------------------
# DoD: an applied edit mutates the draft through apply_edit_op, and is
# traceable to the message that produced it
# --------------------------------------------------------------------------


async def test_a_valid_op_is_applied_and_the_draft_changes(seeded) -> None:
    outcome = await _run(
        seeded,
        "chat_1",
        {"op": "rename_entity", "id": "book", "name": "Title"},
        message="rename Book to Title",
    )
    assert outcome.status == "succeeded"
    assert outcome.outcome == "applied"

    async with seeded() as session:
        row = await session.get(ChatEditRow, "chat_1")
        assert row.applied_op == "rename_entity"
        assert row.summary

        draft = await session.get(CPMDraftRow, PROJECT_ID)
        names = {e["name"] for e in draft.payload["entities"]}
        assert "Title" in names
        assert "Book" not in names


async def test_an_applied_edit_is_traceable_to_its_message(seeded) -> None:
    await _run(
        seeded,
        "chat_2",
        {"op": "rename_entity", "id": "book", "name": "Title"},
        message="please rename Book to Title",
    )

    async with seeded() as session:
        rows = (
            (await session.execute(select(EventRow).where(EventRow.name == "chat_edit_applied")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].payload["message"] == "please rename Book to Title"
    assert rows[0].payload["op"] == "rename_entity"
    assert rows[0].payload["editId"] == "chat_2"
    assert rows[0].project_id == PROJECT_ID
    assert rows[0].account_id == "acct_test"


# --------------------------------------------------------------------------
# DoD: ambiguity is a question, never a silent pick
# --------------------------------------------------------------------------


async def test_a_clarify_response_leaves_the_draft_untouched(seeded) -> None:
    outcome = await _run(
        seeded, "chat_3", {"clarify": "Did you mean Book or Loan?"}, message="rename it"
    )
    assert outcome.outcome == "clarify"

    async with seeded() as session:
        row = await session.get(ChatEditRow, "chat_3")
        assert row.clarify_question == "Did you mean Book or Loan?"
        draft = await session.get(CPMDraftRow, PROJECT_ID)
        assert draft.payload == _draft_payload()


# --------------------------------------------------------------------------
# DoD: a non-edit message never reaches review.edit
# --------------------------------------------------------------------------


async def test_a_non_edit_message_never_touches_the_draft(seeded) -> None:
    outcome = await _run(seeded, "chat_4", {"notAnEdit": True}, message="how's it going?")
    assert outcome.outcome == "not_edit"

    async with seeded() as session:
        row = await session.get(ChatEditRow, "chat_4")
        assert row.applied_op is None
        draft = await session.get(CPMDraftRow, PROJECT_ID)
        assert draft.payload == _draft_payload()

        applied_events = (
            (await session.execute(select(EventRow).where(EventRow.name == "chat_edit_applied")))
            .scalars()
            .all()
        )
    assert applied_events == []


# --------------------------------------------------------------------------
# DoD: a parsed op that fails validation is rejected the same way a
# malformed HTTP request would be -- and fabrication (Watch For) lands here
# --------------------------------------------------------------------------


async def test_an_op_naming_a_nonexistent_entity_is_rejected_not_applied(seeded) -> None:
    # The fabrication risk named in the prompt: phrasing implies an entity
    # ("Invoice" — plausible for a system with fines, not actually in this
    # model) that was never actually there. apply_edit_op is the same
    # function a malformed form submission goes through, so it refuses this
    # exactly as it would refuse a bad HTTP request.
    outcome = await _run(
        seeded,
        "chat_5",
        {"op": "rename_entity", "id": "invoice", "name": "Bill"},
        message="rename Invoice to Bill",
    )
    assert outcome.status == "succeeded"
    assert outcome.outcome == "rejected"

    async with seeded() as session:
        row = await session.get(ChatEditRow, "chat_5")
        assert row.reason
        assert "invoice" in row.reason.lower()

        draft = await session.get(CPMDraftRow, PROJECT_ID)
        assert draft.payload == _draft_payload()

        applied_events = (
            (await session.execute(select(EventRow).where(EventRow.name == "chat_edit_applied")))
            .scalars()
            .all()
        )
    assert applied_events == []


# --------------------------------------------------------------------------
# No model is being reviewed
# --------------------------------------------------------------------------


async def test_a_message_with_no_draft_in_review_fails_cleanly(session_factory) -> None:
    # No `seeded` fixture here on purpose: nothing to parse against.
    await _seed_edit(session_factory, "chat_6", "rename Book to Title")
    outcome = await run_chat_edit(
        "chat_6",
        session_factory=session_factory,
        service=service_returning({"notAnEdit": True}),
    )
    assert outcome.status == "failed"
    assert outcome.error


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------


async def test_a_succeeded_edit_is_not_reparsed(seeded) -> None:
    await _run(seeded, "chat_7", {"notAnEdit": True}, message="hello")

    # A second scripted provider with nothing queued: if this were re-parsed,
    # the exhausted provider would raise and the job would come back failed.
    outcome = await run_chat_edit("chat_7", session_factory=seeded, service=service_returning({}))
    assert outcome.status == "succeeded"
    assert outcome.outcome == "not_edit"


async def test_an_unknown_edit_id_raises(session_factory) -> None:
    with pytest.raises(ChatEditNotFound):
        await run_chat_edit("chat_does_not_exist", session_factory=session_factory)
