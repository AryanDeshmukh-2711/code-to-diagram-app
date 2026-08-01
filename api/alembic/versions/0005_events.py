"""the funnel event log

PRD section 9. Append-only: every metric is a query over this table, so a
number can always be traced back to the events that produced it.

Revision ID: 0005_events
Revises: 0004_billing
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_events"
down_revision: str | None = "0004_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("account_id", sa.String(64), nullable=True),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("tier", sa.String(32), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    for column in ("name", "occurred_at", "account_id", "project_id", "run_id"):
        op.create_index(f"ix_events_{column}", "events", [column])
    # The funnel is always "this account, these steps, in order".
    op.create_index("ix_events_account_name_time", "events", ["account_id", "name", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_events_account_name_time", table_name="events")
    for column in ("name", "occurred_at", "account_id", "project_id", "run_id"):
        op.drop_index(f"ix_events_{column}", table_name="events")
    op.drop_table("events")
