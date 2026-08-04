"""run_extraction end to end against real Postgres, with an injected service
the same way run_chat_edit already takes one.

Written for P-M6-5's fix: POST .../extract's projectName was captured for
ProjectRow only and then discarded, so a fresh project's CPM always ended up
named after the raw project id -- exactly what a review-summary card in chat
would show the user instead of the name they gave it.
"""

import json

import pytest
from extraction_samples import BY_KEY

from extraction.service import ExtractionService
from generation.extraction import ExtractionNotFound, run_extraction
from llm.config import TaskConfig
from llm.gateway import LLMGateway
from llm.providers.scripted import ScriptedProvider
from store.models import CPMDraftRow, ExtractionRow

PROJECT_ID = "proj_extract_test"

TASK = TaskConfig(
    provider="scripted",
    model="stub-model",
    max_tokens=8192,
    temperature=0.0,
    timeout_seconds=60.0,
    system_prompt="Extract a project model.",
)


def service_returning(payload: dict) -> ExtractionService:
    gateway = LLMGateway(
        providers={"scripted": ScriptedProvider([json.dumps(payload)])},
        tasks={"cpm_extraction": TASK},
    )
    return ExtractionService(gateway)


async def _seed_extraction(
    session_factory, extraction_id: str, *, project_name: str | None, text: str
) -> None:
    async with session_factory() as session:
        session.add(
            ExtractionRow(
                id=extraction_id,
                project_id=PROJECT_ID,
                account_id="acct_test",
                input_kind="text",
                project_name=project_name,
                source_text=text,
                status="pending",
            )
        )
        await session.commit()


# --------------------------------------------------------------------------
# P-M6-5: the caller's projectName reaches the CPM, not the raw project id
# --------------------------------------------------------------------------


async def test_a_fresh_extraction_uses_the_requested_project_name(session_factory) -> None:
    sample = BY_KEY["parking_lot"]
    await _seed_extraction(
        session_factory, "ext_named", project_name="My Parking App", text=sample.description
    )

    await run_extraction(
        "ext_named", session_factory=session_factory, service=service_returning(sample.llm_output)
    )

    async with session_factory() as session:
        draft = await session.get(CPMDraftRow, PROJECT_ID)
    assert draft.project_name == "My Parking App"
    assert draft.project_name != PROJECT_ID


async def test_no_requested_name_falls_back_to_the_project_id(session_factory) -> None:
    sample = BY_KEY["parking_lot"]
    await _seed_extraction(
        session_factory, "ext_unnamed", project_name=None, text=sample.description
    )

    await run_extraction(
        "ext_unnamed", session_factory=session_factory, service=service_returning(sample.llm_output)
    )

    async with session_factory() as session:
        draft = await session.get(CPMDraftRow, PROJECT_ID)
    assert draft.project_name == PROJECT_ID


async def test_a_reextraction_with_no_new_name_keeps_the_established_one(session_factory) -> None:
    sample = BY_KEY["parking_lot"]
    async with session_factory() as session:
        session.add(
            CPMDraftRow(
                project_id=PROJECT_ID, project_name="Already Named", payload={"entities": []}
            )
        )
        await session.commit()

    await _seed_extraction(
        session_factory, "ext_reextract", project_name=None, text=sample.description
    )
    await run_extraction(
        "ext_reextract",
        session_factory=session_factory,
        service=service_returning(sample.llm_output),
    )

    async with session_factory() as session:
        draft = await session.get(CPMDraftRow, PROJECT_ID)
    assert draft.project_name == "Already Named"


async def test_a_new_name_on_reextraction_overrides_the_established_one(session_factory) -> None:
    sample = BY_KEY["parking_lot"]
    async with session_factory() as session:
        session.add(
            CPMDraftRow(project_id=PROJECT_ID, project_name="Old Name", payload={"entities": []})
        )
        await session.commit()

    await _seed_extraction(
        session_factory, "ext_renamed", project_name="New Name", text=sample.description
    )
    await run_extraction(
        "ext_renamed", session_factory=session_factory, service=service_returning(sample.llm_output)
    )

    async with session_factory() as session:
        draft = await session.get(CPMDraftRow, PROJECT_ID)
    assert draft.project_name == "New Name"


# --------------------------------------------------------------------------
# The rest of the pipeline, exercised through the same injectable service
# --------------------------------------------------------------------------


async def test_insufficient_input_writes_no_draft(session_factory) -> None:
    vague = BY_KEY["vague_startup"]
    await _seed_extraction(
        session_factory, "ext_vague", project_name="Whatever", text=vague.description
    )

    outcome = await run_extraction(
        "ext_vague", session_factory=session_factory, service=service_returning(vague.llm_output)
    )
    assert outcome.status == "succeeded"
    assert outcome.outcome == "insufficient"

    async with session_factory() as session:
        draft = await session.get(CPMDraftRow, PROJECT_ID)
    assert draft is None


async def test_an_unknown_extraction_id_raises(session_factory) -> None:
    with pytest.raises(ExtractionNotFound):
        await run_extraction("ext_does_not_exist", session_factory=session_factory)


async def test_a_succeeded_extraction_is_not_rerun(session_factory) -> None:
    sample = BY_KEY["parking_lot"]
    await _seed_extraction(
        session_factory, "ext_idempotent", project_name="X", text=sample.description
    )
    await run_extraction(
        "ext_idempotent",
        session_factory=session_factory,
        service=service_returning(sample.llm_output),
    )

    # A second scripted provider with nothing queued: if this were rerun, the
    # exhausted provider would raise and the job would come back failed.
    outcome = await run_extraction(
        "ext_idempotent", session_factory=session_factory, service=service_returning({})
    )
    assert outcome.status == "succeeded"
    assert outcome.outcome == "extracted"
