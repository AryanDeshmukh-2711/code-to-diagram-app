"""The review gate's HTTP surface.

Every structural edit goes through the server rather than being applied in the
browser. That is deliberate: the rename cascade and the validation rules are
CPM semantics, and a second implementation in TypeScript would drift from the
Python one — which is the failure this whole codebase has been arranged to
avoid. A rename is a considered action, not a keystroke, so the round trip
costs nothing the user notices.
"""

import uuid
from typing import Any, Literal

from analytics import events
from analytics.review_signals import ReviewSignals
from cpm.fixtures import library_management_system_payload
from cpm.schema import CPMDraft
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from review import (
    ReviewError,
    add_actor,
    add_attribute,
    add_entity,
    add_relationship,
    confirm_draft,
    delete_actor,
    delete_attribute,
    delete_entity,
    delete_relationship,
    delete_use_case,
    relink_relationship,
    rename_actor,
    rename_entity,
    rename_use_case,
    review_state,
    set_use_case_actors,
)
from review.state import NotConfirmable
from sqlalchemy import func, select
from store.models import CPMDraftRow, CPMVersionRow
from store.session import SessionFactory

from app.core.identity import owned_project, require_account
from app.core.projects import ensure_project

router = APIRouter(prefix="/projects/{project_id}/review", tags=["review"])


class IssueOut(BaseModel):
    code: str
    path: str
    message: str
    explanation: str
    offendingId: str | None = None


class ReviewOut(BaseModel):
    projectId: str
    projectName: str
    draft: dict[str, Any]
    issues: list[IssueOut]
    confirmable: bool
    counts: dict[str, int]
    lastEdit: str | None = None
    referencesUpdated: int = 0


class SeedIn(BaseModel):
    projectName: str = "Library Management System"
    draft: dict[str, Any] | None = None


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


class ConfirmOut(BaseModel):
    versionId: str
    version: int
    confirmedAt: str


def _present(
    row: CPMDraftRow, draft: CPMDraft, summary: str | None = None, touched: int = 0
) -> ReviewOut:
    state = review_state(draft)
    return ReviewOut(
        projectId=row.project_id,
        projectName=row.project_name,
        draft=draft.model_dump(by_alias=True, mode="json"),
        issues=[
            IssueOut(
                code=issue.code,
                path=issue.path,
                message=issue.message,
                explanation=issue.explanation,
                offendingId=issue.offending_id,
            )
            for issue in state.issues
        ],
        confirmable=state.confirmable,
        counts={
            "entities": state.entity_count,
            "relationships": state.relationship_count,
            "actors": state.actor_count,
            "useCases": state.use_case_count,
        },
        lastEdit=summary,
        referencesUpdated=touched,
    )


async def _load(session, project_id: str, account: str) -> CPMDraftRow:
    # One place, so no endpoint can read a draft without proving ownership.
    await owned_project(session, project_id, account)
    row = await session.get(CPMDraftRow, project_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No model is being reviewed for project {project_id!r}.",
        )
    return row


@router.post("/seed", response_model=ReviewOut)
async def seed(project_id: str, body: SeedIn, account: str = Depends(require_account)) -> ReviewOut:
    """Put a model into review.

    With no body this loads the sample project, which is how the screen is
    exercised before extraction is wired to it.
    """
    payload = body.draft if body.draft is not None else library_management_system_payload()
    draft = CPMDraft.model_validate(payload)

    async with SessionFactory() as session:
        row = await session.get(CPMDraftRow, project_id)
        if row is None:
            # A new project is the thing the free tier counts (FR-22). Checked
            # here, in the request, against the database — the button in the
            # browser is a courtesy, not the lock.
            await ensure_project(session, project_id, account, body.projectName)
            row = CPMDraftRow(project_id=project_id)
            session.add(row)
        row.project_name = body.projectName
        row.payload = draft.model_dump(by_alias=True, mode="json")
        await session.commit()
        return _present(row, draft)


@router.get("", response_model=ReviewOut)
async def get_review(project_id: str, account: str = Depends(require_account)) -> ReviewOut:
    async with SessionFactory() as session:
        row = await _load(session, project_id, account)
        return _present(row, CPMDraft.model_validate(row.payload))


@router.post("/edit", response_model=ReviewOut)
async def edit(project_id: str, body: EditIn, account: str = Depends(require_account)) -> ReviewOut:
    async with SessionFactory() as session:
        row = await _load(session, project_id, account)
        draft = CPMDraft.model_validate(row.payload)

        try:
            outcome = _apply(draft, body)
        except ReviewError as exc:
            # 409, not 500: the edit is refused, the model is untouched, and
            # the message is written to be shown next to the field.
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

        row.payload = outcome.draft.model_dump(by_alias=True, mode="json")
        await session.commit()
        return _present(row, outcome.draft, outcome.summary, outcome.references_updated)


def _apply(draft: CPMDraft, body: EditIn):
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


class ConfirmIn(BaseModel):
    """What the review screen observed while the user was on it.

    Sent with the confirmation rather than trickled as separate events: the
    question is what happened *before this decision*, and one payload attached
    to the decision cannot be half-delivered by a closing tab.
    """

    editsTotal: int = 0
    editsByOp: dict[str, int] = Field(default_factory=dict)
    editsReverted: int = 0
    secondsOnScreen: float = 0.0
    activeSeconds: float = 0.0
    itemsViewed: int = 0
    sectionsViewed: list[str] = Field(default_factory=list)
    inspections: int = 0
    issuesAtOpen: int = 0


def _reviewable_items(draft) -> int:
    """How many things there were to look at.

    The denominator for coverage, and the scale for how long a real review
    would take. Counting only the collections the screen actually shows —
    inventing a bigger denominator would make every user look inattentive.
    """
    return sum(
        len(getattr(draft, name, []) or [])
        for name in ("entities", "actors", "relationships", "use_cases")
    )


@router.post("/confirm", response_model=ConfirmOut)
async def confirm(
    project_id: str,
    body: ConfirmIn | None = None,
    account: str = Depends(require_account),
) -> ConfirmOut:
    """The gate (FR-6). Writes an immutable version (FR-7)."""
    async with SessionFactory() as session:
        row = await _load(session, project_id, account)
        draft = CPMDraft.model_validate(row.payload)

        try:
            cpm = confirm_draft(draft, project_name=row.project_name)
        except NotConfirmable as exc:
            # 422: the request was well formed, the model is not ready. The
            # client cannot talk its way past this.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        highest = await session.scalar(
            select(func.max(CPMVersionRow.version)).where(CPMVersionRow.project_id == project_id)
        )
        version = (highest or 0) + 1
        stored = CPMVersionRow(
            id=f"cpmv_{uuid.uuid4().hex[:16]}",
            project_id=project_id,
            version=version,
            payload=cpm.model_dump(by_alias=True, mode="json"),
        )
        session.add(stored)

        # The most important event in the product. Raw signals and verdict
        # together, so the thresholds can be re-argued against history later.
        signals = ReviewSignals(
            edits_total=(body.editsTotal if body else 0),
            edits_by_op=(body.editsByOp if body else {}),
            edits_reverted=(body.editsReverted if body else 0),
            seconds_on_screen=(body.secondsOnScreen if body else 0.0),
            active_seconds=(body.activeSeconds if body else 0.0),
            items_total=_reviewable_items(draft),
            items_viewed=(body.itemsViewed if body else 0),
            sections_viewed=tuple(body.sectionsViewed) if body else (),
            inspections=(body.inspections if body else 0),
            issues_at_open=(body.issuesAtOpen if body else 0),
            issues_at_confirm=0,
        )
        await events.record(
            session,
            events.CPM_CONFIRMED,
            account_id=(account if body else None),
            project_id=project_id,
            payload={**signals.as_payload(), "cpmVersionId": stored.id, "version": version},
        )
        await session.commit()

        return ConfirmOut(
            versionId=stored.id,
            version=version,
            confirmedAt=stored.confirmed_at.isoformat(),
        )
