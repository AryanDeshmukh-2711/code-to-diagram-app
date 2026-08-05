"""remove accounts

The product pivoted from a commercial SaaS to a single-user, local-first
tool: no login, no registration, no per-account ownership checks. There is
nothing left to authenticate a caller against, so the `accounts` table goes
and every `account_id` column that referenced it is relaxed to nullable
rather than dropped -- historical rows keep whatever account they were
stamped with as inert history, and new rows simply leave it unset. No
column anywhere had a real foreign-key constraint against `accounts.id`, so
dropping the table cannot cascade-break anything.

Revision ID: 0011_remove_accounts
Revises: 0010_extraction_project_name
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_remove_accounts"
down_revision: str | None = "0010_extraction_project_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RELAXED = ("projects", "exports", "extractions", "chat_edits")


def upgrade() -> None:
    for table in _RELAXED:
        op.alter_column(table, "account_id", existing_type=sa.String(64), nullable=True)
    op.drop_table("accounts")


def downgrade() -> None:
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
        sa.Column("api_key_hash", sa.String(128), nullable=True),
        sa.Column("api_key_salt", sa.String(32), nullable=True),
    )
    # A real rollback also means reverting the application code -- this only
    # restores the constraint, with a placeholder for whatever rows were
    # written with no account_id in between.
    for table in _RELAXED:
        op.execute(f"UPDATE {table} SET account_id = 'unknown' WHERE account_id IS NULL")
        op.alter_column(
            table,
            "account_id",
            existing_type=sa.String(64),
            nullable=False,
            server_default="unknown",
        )
