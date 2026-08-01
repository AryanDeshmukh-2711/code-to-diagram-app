"""export requests

C-4: exporting moves out of the HTTP request cycle, so the request needs a row
to point at while the worker does the work.

Revision ID: 0006_exports
Revises: 0005_events
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_exports"
down_revision: str | None = "0005_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("tier", sa.String(32), nullable=True),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column(
            "fields", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("watermarked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("content", sa.LargeBinary, nullable=True),
        sa.Column("figures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tables", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("exports")
