"""store.projects: FR-23 (list) and FR-24 (delete, cascading).

Deleting a project has to remove everything it produced without touching a
different project's rows, and without erasing the account's own funnel
history — a project that existed and was later deleted should still be
visible to the metrics this system already reports on.
"""

from datetime import UTC, datetime

from store.models import (
    ChatEditRow,
    CPMDraftRow,
    CPMVersionRow,
    EventRow,
    ExportRow,
    ExtractionRow,
    GenerationArtefactRow,
    GenerationRunRow,
    ProjectRow,
)
from store.projects import delete_project, list_projects

ACCOUNT = "acct_delete_test"


async def _seed_full_project(session_factory, project_id: str) -> None:
    """One project with a row in every table that references it."""
    async with session_factory() as session:
        session.add(ProjectRow(id=project_id, account_id=ACCOUNT, name="Doomed Project"))
        session.add(CPMDraftRow(project_id=project_id, project_name="Doomed Project", payload={}))
        session.add(
            CPMVersionRow(
                id=f"{project_id}_v1",
                project_id=project_id,
                version=1,
                payload={},
                confirmed_at=datetime.now(UTC),
            )
        )
        session.add(
            ExtractionRow(
                id=f"{project_id}_ext",
                project_id=project_id,
                account_id=ACCOUNT,
                input_kind="text",
                source_text="doomed",
                status="succeeded",
            )
        )
        session.add(
            ChatEditRow(
                id=f"{project_id}_chat",
                project_id=project_id,
                account_id=ACCOUNT,
                message="rename Doomed to Renamed",
                status="succeeded",
            )
        )
        run_id = f"{project_id}_run"
        session.add(
            GenerationRunRow(
                id=run_id,
                project_id=project_id,
                cpm_version_id=f"{project_id}_v1",
                account_id=ACCOUNT,
                requested_types=["class"],
                fmt="svg",
                status="succeeded",
                created_at=datetime.now(UTC),
            )
        )
        session.add(
            GenerationArtefactRow(
                id=f"{run_id}_class_svg",
                run_id=run_id,
                diagram_type="class",
                format="svg",
                status="succeeded",
                content=b"<svg></svg>",
            )
        )
        session.add(
            ExportRow(
                id=f"{project_id}_exp",
                run_id=run_id,
                account_id=ACCOUNT,
                format="pdf",
                template_id="ieee-830-plain",
                status="succeeded",
                content=b"%PDF-doomed",
            )
        )
        session.add(
            EventRow(
                id=f"{project_id}_evt",
                account_id=ACCOUNT,
                project_id=project_id,
                name="project_created",
                payload={},
            )
        )
        await session.commit()


async def test_deleting_a_project_removes_every_row_it_produced(session_factory) -> None:
    project_id = "proj_doomed"
    await _seed_full_project(session_factory, project_id)

    async with session_factory() as session:
        project = await session.get(ProjectRow, project_id)
        await delete_project(session, project)

    async with session_factory() as session:
        assert await session.get(ProjectRow, project_id) is None
        assert await session.get(CPMDraftRow, project_id) is None
        assert await session.get(CPMVersionRow, f"{project_id}_v1") is None
        assert await session.get(ExtractionRow, f"{project_id}_ext") is None
        assert await session.get(ChatEditRow, f"{project_id}_chat") is None
        assert await session.get(GenerationRunRow, f"{project_id}_run") is None
        assert await session.get(GenerationArtefactRow, f"{project_id}_run_class_svg") is None
        assert await session.get(ExportRow, f"{project_id}_exp") is None


async def test_deleting_a_project_keeps_its_own_event_history(session_factory) -> None:
    # The funnel log outlives the project it describes -- "created, then
    # deleted" is a fact worth keeping, not something a delete should erase.
    project_id = "proj_doomed_events"
    await _seed_full_project(session_factory, project_id)

    async with session_factory() as session:
        project = await session.get(ProjectRow, project_id)
        await delete_project(session, project)

    async with session_factory() as session:
        assert await session.get(EventRow, f"{project_id}_evt") is not None


async def test_deleting_a_project_never_touches_a_different_one(session_factory) -> None:
    doomed_id, survivor_id = "proj_doomed_iso", "proj_survivor"
    await _seed_full_project(session_factory, doomed_id)
    await _seed_full_project(session_factory, survivor_id)

    async with session_factory() as session:
        project = await session.get(ProjectRow, doomed_id)
        await delete_project(session, project)

    async with session_factory() as session:
        assert await session.get(ProjectRow, doomed_id) is None
        assert await session.get(ProjectRow, survivor_id) is not None
        assert await session.get(CPMDraftRow, survivor_id) is not None
        assert await session.get(GenerationRunRow, f"{survivor_id}_run") is not None
        assert await session.get(GenerationArtefactRow, f"{survivor_id}_run_class_svg") is not None
        assert await session.get(ExportRow, f"{survivor_id}_exp") is not None


async def test_list_projects_returns_only_this_accounts_own_most_recent_first(
    session_factory,
) -> None:
    async with session_factory() as session:
        session.add(ProjectRow(id="proj_mine_old", account_id=ACCOUNT, name="Older"))
        session.add(ProjectRow(id="proj_mine_new", account_id=ACCOUNT, name="Newer"))
        session.add(ProjectRow(id="proj_theirs", account_id="acct_someone_else", name="Not mine"))
        await session.commit()
        # created_at defaults to "now"; force a real ordering rather than
        # trusting two inserts in the same transaction to land microseconds
        # apart in whichever order the test happens to run.
        mine_old = await session.get(ProjectRow, "proj_mine_old")
        mine_old.created_at = datetime(2020, 1, 1, tzinfo=UTC)
        mine_new = await session.get(ProjectRow, "proj_mine_new")
        mine_new.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        await session.commit()

    async with session_factory() as session:
        rows = await list_projects(session, ACCOUNT)

    ids = [row.id for row in rows]
    assert ids == ["proj_mine_new", "proj_mine_old"]
    assert "proj_theirs" not in ids
