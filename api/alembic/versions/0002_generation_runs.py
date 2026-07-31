"""generation runs and their artefacts

Revision ID: 0002_generation
Revises: 0001_review
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_generation"
down_revision: str | None = "0001_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False, index=True),
        sa.Column("cpm_version_id", sa.String(64), nullable=False, index=True),
        sa.Column("template_id", sa.String(64), nullable=True),
        sa.Column("requested_types", postgresql.JSONB, nullable=False),
        sa.Column("fmt", sa.String(8), nullable=False, server_default="svg"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("llm_cost_usd", sa.String(32), nullable=True),
        sa.Column("llm_input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("llm_output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "generation_artefacts",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("diagram_type", sa.String(64), nullable=False),
        sa.Column("format", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("title", sa.String(200), nullable=False, server_default=""),
        sa.Column("engine", sa.String(32), nullable=True),
        sa.Column("source", sa.Text, nullable=True),
        sa.Column("content", sa.LargeBinary, nullable=True),
        sa.Column("storage_key", sa.String(256), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # NFR-R3. This constraint is the idempotency guarantee: a retried run
        # upserts onto its own rows instead of appending a second copy of every
        # diagram.
        sa.UniqueConstraint("run_id", "diagram_type", "format", name="uq_run_artefact"),
    )


def downgrade() -> None:
    op.drop_table("generation_artefacts")
    op.drop_table("generation_runs")
