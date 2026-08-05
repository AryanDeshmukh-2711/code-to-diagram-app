"""Listing and deleting projects, over HTTP (FR-23, FR-24).

The actual work is `store.projects` — this is the thin HTTP wrapper around
it, the same split extraction and chat edits already use between a router
and the shared module a worker or a test can call directly.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel
from store.models import ProjectRow
from store.projects import delete_project as _delete_project
from store.projects import list_projects as _list_projects
from store.session import SessionFactory

from app.core.identity import get_or_404

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectOut(BaseModel):
    projectId: str
    name: str
    createdAt: str


@router.get("", response_model=list[ProjectOut])
async def list_projects() -> list[ProjectOut]:
    """Every project, most recently created first."""
    async with SessionFactory() as session:
        rows = await _list_projects(session)
        return [
            ProjectOut(projectId=row.id, name=row.name, createdAt=row.created_at.isoformat())
            for row in rows
        ]


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str) -> None:
    """Delete a project and everything it produced."""
    async with SessionFactory() as session:
        project = await get_or_404(session, ProjectRow, project_id, "project")
        await _delete_project(session, project)
