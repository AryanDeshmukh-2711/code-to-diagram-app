"""accounts, projects, and the tier a run was generated under

FR-22 and NFR-M4. The tier lands on the run row rather than being looked up
later: margin per tier has to survive people upgrading.

Revision ID: 0004_billing
Revises: 0003_regen
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_billing"
down_revision: str | None = "0003_regen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("tier", sa.String(32), nullable=False, server_default="free"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tier_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column("generation_runs", sa.Column("account_id", sa.String(64), nullable=True))
    op.add_column("generation_runs", sa.Column("tier", sa.String(32), nullable=True))
    op.create_index("ix_generation_runs_account_id", "generation_runs", ["account_id"])
    op.create_index("ix_generation_runs_tier", "generation_runs", ["tier"])


def downgrade() -> None:
    op.drop_index("ix_generation_runs_tier", table_name="generation_runs")
    op.drop_index("ix_generation_runs_account_id", table_name="generation_runs")
    op.drop_column("generation_runs", "tier")
    op.drop_column("generation_runs", "account_id")
    op.drop_table("projects")
    op.drop_table("accounts")
