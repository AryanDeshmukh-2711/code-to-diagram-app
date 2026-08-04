"""Chat edit-intent parsing: one message in, one honest outcome out.

Mirrors `test_extraction_service.py`'s shape for the same reason: the
service's raw output is never trusted, so what matters here is that it comes
back as exactly one of three things, and that a parsed op carries only what
the message actually said.
"""

import json

from chat import ChatEditService, Clarify, NotAnEdit, ParsedEdit
from cpm.fixtures import library_management_system_payload
from cpm.schema import CPMDraft
from llm.config import TaskConfig
from llm.gateway import LLMGateway
from llm.providers.scripted import ScriptedProvider
from review import EditIn

TASK = TaskConfig(
    provider="scripted",
    model="stub-model",
    max_tokens=1024,
    temperature=0.0,
    timeout_seconds=30.0,
    system_prompt="Parse one chat message into an edit intent.",
)


def draft() -> CPMDraft:
    return CPMDraft.model_validate(library_management_system_payload())


def service_returning(payload: dict) -> ChatEditService:
    gateway = LLMGateway(
        providers={"scripted": ScriptedProvider([json.dumps(payload)])},
        tasks={"chat_edit_intent": TASK},
    )
    return ChatEditService(gateway)


async def parse(payload: dict, message: str = "some message"):
    service = service_returning(payload)
    return await service.parse(message, draft())


# --------------------------------------------------------------------------
# The three shapes
# --------------------------------------------------------------------------


async def test_a_clear_message_returns_a_parsed_edit() -> None:
    result = await parse({"op": "rename_entity", "id": "book", "name": "Title"})
    assert isinstance(result, ParsedEdit)
    assert result.edit.op == "rename_entity"
    assert result.edit.id == "book"
    assert result.edit.name == "Title"


async def test_an_ambiguous_message_returns_a_question_not_a_guess() -> None:
    result = await parse({"clarify": "Did you mean the Book entity or the Loan entity?"})
    assert isinstance(result, Clarify)
    assert "Book" in result.question


async def test_a_non_edit_message_is_reported_as_such() -> None:
    result = await parse({"notAnEdit": True})
    assert isinstance(result, NotAnEdit)


async def test_a_response_naming_nothing_is_treated_as_not_an_edit() -> None:
    # Never guess: a raw response that picked none of the three shapes must
    # not be read as an implicit edit.
    result = await parse({})
    assert isinstance(result, NotAnEdit)


async def test_clarify_wins_over_a_half_formed_notanedit() -> None:
    # If the model hedges by setting both, asking wins: a question is never
    # the wrong outcome, where silently discarding the message might be.
    result = await parse({"notAnEdit": True, "clarify": "did you mean X or Y?"})
    assert isinstance(result, Clarify)


async def test_clarify_wins_over_a_half_formed_op() -> None:
    # If the model hedges by setting both, asking wins: guessing an op because
    # a clarify string is also present would be exactly the silent pick this
    # whole path exists to avoid.
    result = await parse({"op": "delete_entity", "id": "book", "clarify": "which one?"})
    assert isinstance(result, Clarify)


# --------------------------------------------------------------------------
# The parsed edit carries only what the op needs
# --------------------------------------------------------------------------


async def test_a_parsed_edit_only_carries_the_fields_that_op_needs() -> None:
    result = await parse({"op": "delete_entity", "id": "book", "name": "should be ignored"})
    assert isinstance(result, ParsedEdit)
    assert isinstance(result.edit, EditIn)
    # delete_entity uses only `id`; the model padding out `name` besides is
    # exactly the kind of unrequested extra a chat parse must not smuggle in
    # as if it were part of the op. apply_edit_op will simply never read it.
    assert result.edit.id == "book"


async def test_add_relationship_carries_its_own_fields() -> None:
    result = await parse(
        {
            "op": "add_relationship",
            "fromId": "member",
            "toId": "book",
            "type": "association",
            "label": "borrows",
        }
    )
    assert isinstance(result, ParsedEdit)
    assert result.edit.op == "add_relationship"
    assert result.edit.fromId == "member"
    assert result.edit.toId == "book"
    assert result.edit.label == "borrows"


async def test_set_use_case_actors_carries_the_actor_list() -> None:
    result = await parse(
        {"op": "set_use_case_actors", "id": "uc-borrow-book", "actorIds": ["member", "librarian"]}
    )
    assert isinstance(result, ParsedEdit)
    assert result.edit.actorIds == ["member", "librarian"]


# --------------------------------------------------------------------------
# Data, not instructions (FR-3/NFR-S3)
# --------------------------------------------------------------------------


async def test_the_message_and_the_model_are_sent_as_one_data_block() -> None:
    provider = ScriptedProvider([json.dumps({"notAnEdit": True})])
    gateway = LLMGateway(providers={"scripted": provider}, tasks={"chat_edit_intent": TASK})
    service = ChatEditService(gateway)
    await service.parse("rename Book to Title", draft())

    assert len(provider.requests) == 1
    user_message = provider.requests[0].user
    assert "<untrusted_input>" in user_message
    assert "rename Book to Title" in user_message
    assert "Book" in user_message  # the current model is in the same block
