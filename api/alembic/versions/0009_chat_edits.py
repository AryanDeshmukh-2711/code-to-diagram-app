"""chat edit intents

P-M6-2: one chat message -> a candidate edit op, applied through the same
path review/edit already uses (C-3). status is the job lifecycle; outcome
(set only once succeeded) is "applied", "clarify", "not_edit", or "rejected"
-- a message that turns out ambiguous, off-topic, or semantically invalid is
a succeeded parse, not a failure.

Revision ID: 0009_chat_edits
Revises: 0008_extractions
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_chat_edits"
down_revision: str | None = "0008_extractions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_edits",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("applied_op", sa.String(32), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("references_updated", sa.Integer, nullable=True),
        sa.Column("clarify_question", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
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
    op.create_index("ix_chat_edits_project_id", "chat_edits", ["project_id"])
    op.create_index("ix_chat_edits_account_id", "chat_edits", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_edits_account_id", table_name="chat_edits")
    op.drop_index("ix_chat_edits_project_id", table_name="chat_edits")
    op.drop_table("chat_edits")
