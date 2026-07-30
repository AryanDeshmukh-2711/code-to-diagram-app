"""The CPM review gate — the product's trust mechanism.

Extraction is probabilistic; rendering is deterministic. This package is the
human checkpoint between them, and it is the single control for risk R1 (a
plausible-but-wrong artefact reaching a submission).
"""

from review.errors import (
    InvalidName,
    NameCollision,
    ReviewError,
    UnknownElement,
)
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
from review.state import (
    NotConfirmable,
    ReviewIssue,
    ReviewState,
    confirm_draft,
    review_state,
)

__all__ = [
    "EditOutcome",
    "InvalidName",
    "NameCollision",
    "NotConfirmable",
    "ReviewError",
    "ReviewIssue",
    "ReviewState",
    "UnknownElement",
    "add_actor",
    "add_attribute",
    "add_entity",
    "add_relationship",
    "confirm_draft",
    "delete_actor",
    "delete_attribute",
    "delete_entity",
    "delete_relationship",
    "delete_use_case",
    "relink_relationship",
    "rename_actor",
    "rename_entity",
    "rename_use_case",
    "review_state",
    "set_use_case_actors",
]
