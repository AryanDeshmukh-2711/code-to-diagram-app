"""Persistence shared by the api and the worker.

These live in `shared/` for the same reason the CPM does: the API creates a run
and the worker fills it in, and two SQLAlchemy declarations of the same table
would drift. One definition, imported by both.

The idempotency guarantee (NFR-R3) is a database constraint, not a convention.
`uq_run_artefact` on (run_id, diagram_type, format) makes a duplicate artefact
impossible to insert, so a job that is retried — by arq, by a worker crash, by
someone pressing the button twice — overwrites its own row rather than adding a
second one. Deterministic mappers (FR-9) mean the overwrite is byte-identical.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """One metadata object for every table in the product."""


def _now() -> datetime:
    return datetime.now(UTC)


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunKind(StrEnum):
    FULL = "full"
    REGENERATION = "regeneration"
    """FR-12. A regeneration is a run in its own right rather than an edit of
    the previous one: it renders one diagram, carries the rest forward, and
    ends up a complete artefact set. That keeps "export a run" meaning the same
    thing for both kinds, and keeps the old set intact so a user can see what
    was regenerated and when."""


class ArtefactStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    """Not in the original four. A diagram the model never described is
    neither a success nor a failure, and reporting it as failed would tell a
    user something is broken when nothing is."""


class AccountRow(Base):
    """Who owns the work, and what they are entitled to (FR-22).

    The tier is stored rather than derived so that a plan change is an event
    with a date, and so a run can record the tier it was generated under —
    which is what makes the margin query answerable after somebody upgrades.
    """

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    tier_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectRow(Base):
    """One project. Counted against the account's project quota."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class CPMDraftRow(Base):
    """The model the user is currently editing. One per project."""

    __tablename__ = "cpm_drafts"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class CPMVersionRow(Base):
    """A confirmed model. Written once, never updated (FR-7)."""

    __tablename__ = "cpm_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_cpm_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class GenerationRunRow(Base):
    """One end-to-end execution producing an artefact set (SRS §6.2)."""

    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cpm_version_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    """The tier in force when this run happened, not the account's tier today.
    NFR-M4 asks what a plan costs to serve; an upgrade six weeks later must not
    silently rewrite the history of what the cheap plan cost."""

    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=RunKind.FULL)
    parent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    """Set on a regeneration. Walking it back gives the lineage of a set —
    which diagram was redrawn, when, and what it was redrawn from."""

    requested_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    """What this run actually rendered. On a regeneration that is the single
    diagram; the rest of the set is carried forward from the parent."""

    fmt: Mapped[str] = mapped_column(String(8), nullable=False, default="svg")

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RunStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    llm_cost_usd: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """Decimal as a string, so no float rounding creeps into a money column.
    Null means unmeasured; "0" means measured and free (NFR-M3)."""

    llm_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GenerationArtefactRow(Base):
    """One diagram in one run. The unique constraint is the idempotency."""

    __tablename__ = "generation_artefacts"
    __table_args__ = (UniqueConstraint("run_id", "diagram_type", "format", name="uq_run_artefact"),)

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    diagram_type: Mapped[str] = mapped_column(String(64), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ArtefactStatus.PENDING)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    engine: Mapped[str | None] = mapped_column(String(32), nullable=True)

    cpm_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Which model this figure actually depicts. After a regeneration against a
    newer version, the carried-forward artefacts still name their own — so
    "this diagram is from an older model" is a recorded fact rather than an
    inference."""

    origin_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """The run that rendered these bytes. Differs from `run_id` on a carried-
    forward artefact, which is what makes "only this one was regenerated"
    visible in the artefact list rather than only in the run row."""

    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    """Null while artefacts live in the database. Diagrams are 10–30KB and a
    whole run is under a megabyte, so object storage is not yet pulling its
    weight — but the column exists so moving to R2 is a backfill, not a
    migration of the read path."""

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
