"""extraction requests

P-M6-1: text/PDF -> CPM draft, off the request cycle (C-4). status is the job
lifecycle; outcome (set only once succeeded) is "extracted" or "insufficient"
-- hitting the FR-5 floor is a succeeded, honest outcome, not a failure.

Revision ID: 0008_extractions
Revises: 0007_auth
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_extractions"
down_revision: str | None = "0007_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extractions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("input_kind", sa.String(8), nullable=False),
        sa.Column("source_text", sa.Text, nullable=True),
        sa.Column("source_pdf", sa.LargeBinary, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("entities_found", sa.Integer, nullable=True),
        sa.Column("relationships_found", sa.Integer, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "guidance", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("notes", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cpm_draft_ready", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_extractions_project_id", "extractions", ["project_id"])
    op.create_index("ix_extractions_account_id", "extractions", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_extractions_account_id", table_name="extractions")
    op.drop_index("ix_extractions_project_id", table_name="extractions")
    op.drop_table("extractions")
