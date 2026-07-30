"""cpm drafts and immutable cpm versions

Revision ID: 0001_review
Revises:
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_review"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cpm_drafts",
        sa.Column("project_id", sa.String(64), primary_key=True),
        sa.Column("project_name", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cpm_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_cpm_version"),
    )

    # FR-7 immutability, enforced by the database rather than by convention.
    # A confirmed model is the evidence of what the user signed off; a stray
    # UPDATE in some future migration script would rewrite history silently.
    op.execute("CREATE RULE cpm_versions_no_update AS ON UPDATE TO cpm_versions DO INSTEAD NOTHING")
    op.execute("CREATE RULE cpm_versions_no_delete AS ON DELETE TO cpm_versions DO INSTEAD NOTHING")


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS cpm_versions_no_delete ON cpm_versions")
    op.execute("DROP RULE IF EXISTS cpm_versions_no_update ON cpm_versions")
    op.drop_table("cpm_versions")
    op.drop_table("cpm_drafts")
