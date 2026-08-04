"""EditIn: the one shape an edit request can arrive in.

A human filling in the review screen's form and a chat message parsed into an
intent both end up here, and `apply_edit_op` is the one dispatcher either path
calls (C-3). There is exactly one way an edit reaches the CPM's operations —
never two implementations that could drift, never a chat-only shortcut around
the validation a form submission would have to pass.
"""

from typing import Literal

from pydantic import BaseModel, Field

from cpm.schema import CPMDraft
from review.operations import (
    EditOutcome,
    add_actor,
    add_attribute,
    add_entity,
    add_relationship,
    delete_actor,
    delete_attribute,
    delete_entity,
    delete_relationship,
    delete_use_case,
    relink_relationship,
    rename_actor,
    rename_entity,
    rename_use_case,
    set_use_case_actors,
)

EDIT_OPS = (
    "rename_entity",
    "rename_actor",
    "rename_use_case",
    "delete_entity",
    "delete_actor",
    "delete_relationship",
    "delete_use_case",
    "delete_attribute",
    "add_entity",
    "add_actor",
    "add_attribute",
    "add_relationship",
    "relink_relationship",
    "set_use_case_actors",
)


class EditIn(BaseModel):
    op: Literal[
        "rename_entity",
        "rename_actor",
        "rename_use_case",
        "delete_entity",
        "delete_actor",
        "delete_relationship",
        "delete_use_case",
        "delete_attribute",
        "add_entity",
        "add_actor",
        "add_attribute",
        "add_relationship",
        "relink_relationship",
        "set_use_case_actors",
    ]
    id: str | None = None
    name: str | None = None
    entityId: str | None = None
    fromId: str | None = None
    toId: str | None = None
    type: str | None = None
    label: str | None = None
    cardinality: str | None = None
    attributeName: str | None = None
    attributeType: str | None = None
    actorIds: list[str] = Field(default_factory=list)


def apply_edit_op(draft: CPMDraft, body: EditIn) -> EditOutcome:
    op = body.op
    if op == "rename_entity":
        return rename_entity(draft, body.id or "", body.name or "")
    if op == "rename_actor":
        return rename_actor(draft, body.id or "", body.name or "")
    if op == "rename_use_case":
        return rename_use_case(draft, body.id or "", body.name or "")
    if op == "delete_entity":
        return delete_entity(draft, body.id or "")
    if op == "delete_actor":
        return delete_actor(draft, body.id or "")
    if op == "delete_relationship":
        return delete_relationship(draft, body.id or "")
    if op == "delete_use_case":
        return delete_use_case(draft, body.id or "")
    if op == "delete_attribute":
        return delete_attribute(draft, body.entityId or "", body.attributeName or "")
    if op == "add_entity":
        return add_entity(draft, body.name or "")
    if op == "add_actor":
        return add_actor(draft, body.name or "")
    if op == "add_attribute":
        return add_attribute(
            draft, body.entityId or "", body.attributeName or "", body.attributeType or "string"
        )
    if op == "add_relationship":
        return add_relationship(
            draft,
            body.fromId or "",
            body.toId or "",
            body.type or "association",
            body.label,
            body.cardinality,
        )
    if op == "relink_relationship":
        return relink_relationship(
            draft,
            body.id or "",
            body.fromId,
            body.toId,
            body.type,
            body.label,
            body.cardinality,
        )
    return set_use_case_actors(draft, body.id or "", body.actorIds)
