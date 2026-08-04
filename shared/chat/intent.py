"""What the model is allowed to say about one chat message.

Deliberately looser than `review.EditIn`: every field is optional, because the
model's raw guess is never trusted directly (C-3). It is read into this shape,
and only the fields relevant to whichever branch fired are used to build the
real `EditIn` — the same model a form submission builds, which is what
actually gets to touch the CPM.
"""

from typing import Literal

from pydantic import BaseModel, Field

EditOp = Literal[
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


class ChatEditIntent(BaseModel):
    """The model's raw read of one chat message. Exactly one of three shapes:

    - `op` set: a candidate edit. Only the fields that op needs should be set.
    - `clarify` set: the message was ambiguous; this is the question to ask back.
    - `notAnEdit` true: the message was not a request to change the model.
    """

    op: EditOp | None = None
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
    clarify: str | None = None
    notAnEdit: bool = False
