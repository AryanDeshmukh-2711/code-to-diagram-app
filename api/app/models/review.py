"""Persistence for the review gate.

Two tables with deliberately different characters. A draft is scratch space and
is overwritten on every edit. A confirmed version is evidence — FR-7 wants it
immutable so an artefact set can always be traced to the exact model that
produced it, and R5 wants an audit trail of what the user actually signed off.

Immutability is enforced by the database, not by everyone remembering not to
write an UPDATE. See the migration's rule on cpm_versions.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


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
