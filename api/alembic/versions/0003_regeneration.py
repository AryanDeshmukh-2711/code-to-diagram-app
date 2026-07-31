"""selective regeneration (FR-12)

Adds the lineage a regeneration needs: a run knows its kind and its parent, and
an artefact knows which model it depicts and which run drew it.

Revision ID: 0003_regen
Revises: 0002_generation
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_regen"
down_revision: str | None = "0002_generation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "generation_runs",
        sa.Column("kind", sa.String(16), nullable=False, server_default="full"),
    )
    op.add_column("generation_runs", sa.Column("parent_run_id", sa.String(64), nullable=True))
    op.create_index("ix_generation_runs_parent_run_id", "generation_runs", ["parent_run_id"])

    # Nullable, and backfilled from the run: artefacts written before this
    # migration were all drawn by their own run, from that run's version.
    op.add_column("generation_artefacts", sa.Column("cpm_version_id", sa.String(64), nullable=True))
    op.add_column("generation_artefacts", sa.Column("origin_run_id", sa.String(64), nullable=True))
    op.execute(
        """
        UPDATE generation_artefacts a
           SET origin_run_id = a.run_id,
               cpm_version_id = r.cpm_version_id
          FROM generation_runs r
         WHERE r.id = a.run_id
        """
    )


def downgrade() -> None:
    op.drop_column("generation_artefacts", "origin_run_id")
    op.drop_column("generation_artefacts", "cpm_version_id")
    op.drop_index("ix_generation_runs_parent_run_id", table_name="generation_runs")
    op.drop_column("generation_runs", "parent_run_id")
    op.drop_column("generation_runs", "kind")
