"""Listing and deleting a user's own projects, over HTTP (FR-23, FR-24).

The actual work is `store.projects` — this is the thin HTTP wrapper around
it, the same split extraction and chat edits already use between a router
and the shared module a worker or a test can call directly.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from store.projects import delete_project as _delete_project
from store.projects import list_projects as _list_projects
from store.session import SessionFactory

from app.core.identity import owned_project, require_account

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectOut(BaseModel):
    projectId: str
    name: str
    createdAt: str


@router.get("", response_model=list[ProjectOut])
async def list_projects(account: str = Depends(require_account)) -> list[ProjectOut]:
    """Every project this account owns, most recently created first."""
    async with SessionFactory() as session:
        rows = await _list_projects(session, account_id=account)
        return [
            ProjectOut(projectId=row.id, name=row.name, createdAt=row.created_at.isoformat())
            for row in rows
        ]


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, account: str = Depends(require_account)) -> None:
    """Delete a project and everything it produced — never someone else's
    (owned_project 404s rather than 403s, so a miss does not confirm the id
    exists for an account that does not own it)."""
    async with SessionFactory() as session:
        project = await owned_project(session, project_id, account)
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no project {project_id!r}")
        await _delete_project(session, project)
