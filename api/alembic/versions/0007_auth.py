"""account credentials

The pre-launch review's remaining High finding: identity was asserted, never
proved. An account now holds a hashed API key, and a request carries a signed
session token minted from it.

Revision ID: 0007_auth
Revises: 0006_exports
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_auth"
down_revision: str | None = "0006_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("api_key_hash", sa.String(128), nullable=True))
    op.add_column("accounts", sa.Column("api_key_salt", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "api_key_salt")
    op.drop_column("accounts", "api_key_hash")
