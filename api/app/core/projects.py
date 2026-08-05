"""Creating a project, the one way it is allowed to happen.

A project comes into being the first time something is put in front of it —
today that is `review.seed`; as of P-M6-1 it is also `POST .../extract`. Both
call this, so the funnel's `project_created` event fires from one place
rather than two that could quietly drift apart.
"""

from analytics import events
from store.models import AccountRow, ProjectRow


async def ensure_project(session, project_id: str, account_id: str, project_name: str) -> None:
    """If this project does not exist yet, create it.

    Does nothing if the project already exists: an established project is
    not a new one to create.
    """
    existing = await session.get(ProjectRow, project_id)
    if existing is not None:
        return

    if await session.get(AccountRow, account_id) is None:
        session.add(AccountRow(id=account_id))
    session.add(ProjectRow(id=project_id, account_id=account_id, name=project_name))
    await events.record(
        session,
        events.PROJECT_CREATED,
        account_id=account_id,
        project_id=project_id,
        payload={"projectName": project_name},
    )
