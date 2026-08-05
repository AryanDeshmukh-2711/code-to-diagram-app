"""Listing and deleting a project's own data (FR-23, FR-24).

Deleting removes everything a project produced — draft, confirmed versions,
runs, artefacts, exports, extractions, chat edits — but not its `EventRow`
history. Those are the account's funnel log, not the project itself, and
erasing them would make "a project was created and later deleted" invisible
to the metrics this system already reports on.

Bounded, synchronous database work — nothing here touches a model or an
engine, so none of it needs the worker (C-4 governs work that must not block
the request cycle; a handful of DELETE statements across a project's own rows
is not that). FR-24's "within 24 hours" is satisfied by doing it immediately:
nothing in this stack has moved an artefact to real object storage yet, so
there is no async cleanup step to defer to.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from store.models import (
    ChatEditRow,
    CPMDraftRow,
    CPMVersionRow,
    ExportRow,
    ExtractionRow,
    GenerationArtefactRow,
    GenerationRunRow,
    ProjectRow,
)


async def list_projects(session: AsyncSession) -> list[ProjectRow]:
    """Every project, most recently created first."""
    rows = await session.scalars(select(ProjectRow).order_by(ProjectRow.created_at.desc()))
    return list(rows)


async def delete_project(session: AsyncSession, project: ProjectRow) -> None:
    """Delete `project` and everything it produced."""
    run_ids = list(
        await session.scalars(
            select(GenerationRunRow.id).where(GenerationRunRow.project_id == project.id)
        )
    )
    if run_ids:
        await session.execute(
            delete(GenerationArtefactRow).where(GenerationArtefactRow.run_id.in_(run_ids))
        )
        await session.execute(delete(ExportRow).where(ExportRow.run_id.in_(run_ids)))

    await session.execute(delete(GenerationRunRow).where(GenerationRunRow.project_id == project.id))
    await session.execute(delete(CPMVersionRow).where(CPMVersionRow.project_id == project.id))
    await session.execute(delete(CPMDraftRow).where(CPMDraftRow.project_id == project.id))
    await session.execute(delete(ExtractionRow).where(ExtractionRow.project_id == project.id))
    await session.execute(delete(ChatEditRow).where(ChatEditRow.project_id == project.id))
    await session.delete(project)
    await session.commit()
