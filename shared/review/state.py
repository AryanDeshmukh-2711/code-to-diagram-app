"""What the review screen needs to know, and the gate out of it.

FR-6 says generation must not proceed until the user confirms. That is
enforced by the type system rather than by a check somebody could forget:
`execute_generation_run` takes a `CPM`, a draft is a `CPMDraft`, and the only
way to turn one into the other is `confirm_draft`. There is no code path from
an unconfirmed model to a rendered diagram.

FR-7 wants each confirmed model stored as an immutable version. `confirm_draft`
returns the CPM that the API persists; the persisted row is never updated.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from cpm.integrity import IntegrityIssue, check_integrity
from cpm.schema import CPM, CPMDraft
from review.errors import ReviewError

# Guidance keyed by issue code, written for someone who has never seen a UML
# diagram. "unknown_entity_ref" means nothing to a second-year student.
_EXPLANATIONS = {
    "duplicate_id": "Two items share an identity. Rename one of them.",
    "duplicate_entity_name": "Two things have the same name. Merge them, or rename one.",
    "duplicate_actor_name": "Two people have the same name. Merge them, or rename one.",
    "unknown_entity_ref": (
        "This points at a thing that is not in the list. Re-link it or remove it."
    ),
    "unknown_actor_ref": "This lists a person who is not in the Who uses it list.",
    "unknown_component_ref": "This refers to a part that no longer exists.",
    "unknown_participant_ref": "This step involves someone or something not in the list.",
    "step_endpoint_not_a_participant": "This step talks to someone not taking part in it.",
    "unknown_state_ref": "This leads to a status that does not exist.",
    "state_transition_crosses_entity": "This status change jumps between two different things.",
    "duplicate_step_order": "Two steps claim the same position in the sequence.",
}


@dataclass(frozen=True)
class ReviewIssue:
    """One problem, addressed to the user rather than to a developer."""

    code: str
    path: str
    message: str
    explanation: str
    offending_id: str | None = None

    @classmethod
    def of(cls, issue: IntegrityIssue) -> "ReviewIssue":
        return cls(
            code=issue.code.value,
            path=issue.path,
            message=issue.message,
            explanation=_EXPLANATIONS.get(issue.code.value, "This needs fixing before generating."),
            offending_id=issue.offending_id,
        )


@dataclass(frozen=True)
class ReviewState:
    issues: list[ReviewIssue] = field(default_factory=list)
    entity_count: int = 0
    relationship_count: int = 0
    actor_count: int = 0
    use_case_count: int = 0

    @property
    def confirmable(self) -> bool:
        """Whether Generate can be pressed at all."""
        return not self.issues and self.entity_count > 0

    def issues_for(self, path_prefix: str) -> list[ReviewIssue]:
        return [issue for issue in self.issues if issue.path.startswith(path_prefix)]


def review_state(draft: CPMDraft) -> ReviewState:
    return ReviewState(
        issues=[ReviewIssue.of(issue) for issue in check_integrity(draft)],
        entity_count=len(draft.entities),
        relationship_count=len(draft.relationships),
        actor_count=len(draft.actors),
        use_case_count=len(draft.use_cases),
    )


class NotConfirmable(ReviewError):
    """The draft still has problems, so it cannot be confirmed."""

    def __init__(self, state: ReviewState) -> None:
        if state.entity_count == 0:
            super().__init__("There is nothing to generate from — add at least one thing.")
        else:
            listed = "\n".join(f"  • {issue.explanation} ({issue.path})" for issue in state.issues)
            super().__init__(f"Fix these before generating:\n{listed}")
        self.state = state


def confirm_draft(
    draft: CPMDraft,
    *,
    project_name: str,
    authors: list[str] | None = None,
    created_at: datetime | None = None,
) -> CPM:
    """Turn a reviewed draft into a CPM. This is the gate (FR-6).

    Raises `NotConfirmable` if the draft still has issues — so a caller cannot
    confirm past a broken model even deliberately.
    """
    state = review_state(draft)
    if not state.confirmable:
        raise NotConfirmable(state)

    return CPM.model_validate(
        {
            **draft.model_dump(by_alias=True, exclude={"meta"}),
            "meta": {
                "projectName": project_name,
                "authors": authors or [],
                "createdAt": created_at or datetime.now(UTC),
            },
        }
    )
