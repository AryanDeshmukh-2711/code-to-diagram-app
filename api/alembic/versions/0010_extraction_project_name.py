"""extraction project name

P-M6-5: the project name a caller gave POST .../extract was being used only
to seed ProjectRow.name and then discarded -- run_extraction had no way to
give a fresh CPM's meta.projectName anything but the raw project id, which
is exactly what the review-summary card was showing instead of a real name.

Revision ID: 0010_extraction_project_name
Revises: 0009_chat_edits
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_extraction_project_name"
down_revision: str | None = "0009_chat_edits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("extractions", sa.Column("project_name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("extractions", "project_name")
