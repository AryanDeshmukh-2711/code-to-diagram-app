"""Structural strictness of the CPM models.

These assert the model rejects malformed input outright rather than coercing or
silently dropping it. An LLM that emits an unexpected key is a signal, not
noise — swallowing it is how a field quietly stops being populated.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from cpm.schema import (
    CPM,
    Actor,
    Attribute,
    CPMDraft,
    Entity,
    FlowStep,
    Relationship,
    RelationshipType,
    Requirement,
)


def test_fixture_payload_builds_a_cpm(payload: dict[str, Any]) -> None:
    assert isinstance(CPM.model_validate(payload), CPM)


def test_unknown_field_is_rejected(payload: dict[str, Any]) -> None:
    payload["entities"][0]["colour"] = "blue"
    with pytest.raises(ValidationError, match="colour"):
        CPM.model_validate(payload)


def test_unknown_top_level_field_is_rejected(payload: dict[str, Any]) -> None:
    payload["diagrams"] = []
    with pytest.raises(ValidationError, match="diagrams"):
        CPM.model_validate(payload)


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_entity_name_cannot_be_blank(name: str) -> None:
    with pytest.raises(ValidationError):
        Entity(id="book", name=name)


def test_entity_names_are_whitespace_stripped() -> None:
    assert Entity(id="book", name="  Book  ").name == "Book"


@pytest.mark.parametrize("bad_id", ["Book", "book_id", "-book", "book ", "", "café"])
def test_ids_must_be_url_safe_slugs(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        Entity(id=bad_id, name="Book")


def test_relationship_type_must_be_a_known_uml_relationship() -> None:
    with pytest.raises(ValidationError):
        Relationship.model_validate(
            {"id": "r1", "from": "book", "to": "loan", "type": "sort-of-related"}
        )


def test_relationship_accepts_every_declared_uml_type() -> None:
    for relationship_type in RelationshipType:
        built = Relationship.model_validate(
            {"id": "r1", "from": "book", "to": "loan", "type": relationship_type.value}
        )
        assert built.type is relationship_type


def test_relationship_reads_and_writes_the_json_from_key() -> None:
    # "from" is a Python keyword, so the field is from_ internally. The wire
    # format must still be "from" — a diagram renderer reading "from_" would
    # silently see nothing.
    built = Relationship.model_validate(
        {"id": "r1", "from": "book", "to": "loan", "type": "association"}
    )
    assert built.from_ == "book"

    dumped = built.model_dump(by_alias=True)
    assert dumped["from"] == "book"
    assert "from_" not in dumped


def test_flow_step_reads_and_writes_the_json_from_key() -> None:
    step = FlowStep.model_validate(
        {"from": "member", "to": "book", "message": "borrow()", "order": 1}
    )
    assert step.from_ == "member"
    assert step.model_dump(by_alias=True)["from"] == "member"


@pytest.mark.parametrize("order", [0, -1])
def test_flow_step_order_must_be_positive(order: int) -> None:
    with pytest.raises(ValidationError):
        FlowStep.model_validate({"from": "a", "to": "b", "message": "m", "order": order})


def test_requirement_type_is_constrained() -> None:
    with pytest.raises(ValidationError):
        Requirement.model_validate(
            {"id": "r1", "type": "aspirational", "text": "x", "priority": "P0"}
        )


def test_attribute_flags_default_to_false() -> None:
    attribute = Attribute(name="title", type="string")
    assert attribute.is_key is False
    assert attribute.is_required is False


def test_actor_is_primary_defaults_to_false() -> None:
    assert Actor(id="member", name="Member").is_primary is False


def test_meta_requires_a_project_name(payload: dict[str, Any]) -> None:
    del payload["meta"]["projectName"]
    with pytest.raises(ValidationError, match="projectName"):
        CPM.model_validate(payload)


def test_round_trip_through_json_is_lossless(payload: dict[str, Any]) -> None:
    original = CPM.model_validate(payload)
    restored = CPM.model_validate_json(original.model_dump_json(by_alias=True))
    assert restored == original


def test_draft_allows_broken_references_but_cpm_does_not(payload: dict[str, Any]) -> None:
    # The review gate needs to hold a structurally-valid but not-yet-consistent
    # model so it can show the user what to fix. CPMDraft is that state.
    payload["relationships"][0]["from"] = "does-not-exist"

    assert isinstance(CPMDraft.model_validate(payload), CPMDraft)
    with pytest.raises(ValidationError):
        CPM.model_validate(payload)
