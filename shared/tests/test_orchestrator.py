"""Orchestration against a real database.

These tests talk to Postgres on purpose. The idempotency guarantee (NFR-R3) is
`uq_run_artefact` plus ON CONFLICT DO UPDATE — it lives in the database, not in
Python — so a fake session factory would assert that the mock behaved like a
mock. The interesting question is what happens when two writes of the same
diagram reach the same table, and only the table can answer it.

Everything is created in a throwaway schema so a test run cannot touch
development data, and so the FR-7 immutability rules on `cpm_versions` (which
would block cleanup) are not in the way.
"""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cpm.fixtures import load_library_management_system
from diagrams.mapper import DiagramMapper, InsufficientModelData
from diagrams.registry import registry
from diagrams.renderer import DiagramRenderer
from diagrams.types import RenderFormat
from generation.orchestrator import RunNotFound, artefacts_of, execute_run
from store.models import (
    ArtefactStatus,
    Base,
    CPMVersionRow,
    GenerationRunRow,
    RunStatus,
)
from store.session import database_url

SCHEMA = "orchestrator_test"
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"


class AlwaysRenders:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    async def render(self, source: str, fmt: RenderFormat) -> bytes:
        self.calls += 1
        return SVG


class AlwaysFails:
    def __init__(self, name: str) -> None:
        self.name = name

    async def render(self, source: str, fmt: RenderFormat) -> bytes:
        from diagrams.engines.base import EngineUnavailable

        raise EngineUnavailable("engine is down")


def renderer(ok: bool = True, mappers=None) -> DiagramRenderer:
    factory = AlwaysRenders if ok else AlwaysFails
    return DiagramRenderer(
        engines={"plantuml": factory("plantuml"), "mermaid": factory("mermaid")},
        mappers=mappers,
    )


@pytest.fixture
async def session_factory():
    """A private schema, dropped afterwards. Skips loudly if there is no
    database — silently passing would leave the only real proof of idempotency
    quietly unexercised."""
    url = os.getenv("TEST_DATABASE_URL", database_url())
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            await connection.execute(text(f"CREATE SCHEMA {SCHEMA}"))
    except Exception as exc:  # pragma: no cover - environment, not logic
        await engine.dispose()
        pytest.skip(f"no Postgres at {url}: {type(exc).__name__}: {exc}")

    scoped = engine.execution_options(schema_translate_map={None: SCHEMA})
    async with scoped.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(scoped, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    await engine.dispose()


@pytest.fixture
async def seeded(session_factory):
    """A confirmed CPM version and a pending run over every registered type."""
    cpm = load_library_management_system()
    async with session_factory() as session:
        session.add(
            CPMVersionRow(
                id="ver_test",
                project_id="proj_test",
                version=1,
                payload=cpm.model_dump(by_alias=True, mode="json"),
                confirmed_at=datetime.now(UTC),
            )
        )
        session.add(
            GenerationRunRow(
                id="run_test",
                project_id="proj_test",
                cpm_version_id="ver_test",
                requested_types=sorted(registry()),
                fmt="svg",
                status=RunStatus.PENDING,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    return "run_test"


async def _run_row(session_factory, run_id: str) -> GenerationRunRow:
    async with session_factory() as session:
        return await session.get(GenerationRunRow, run_id)


async def _force_status(session_factory, run_id: str, status: str) -> None:
    async with session_factory() as session:
        run = await session.get(GenerationRunRow, run_id)
        run.status = status
        await session.commit()


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


async def test_a_run_persists_one_artefact_per_requested_type(session_factory, seeded) -> None:
    outcome = await execute_run(seeded, renderer(), session_factory=session_factory)
    rows = await artefacts_of(seeded, session_factory=session_factory)

    assert outcome.status == RunStatus.SUCCEEDED
    assert len(rows) == len(registry())
    assert {row.diagram_type for row in rows} == set(registry())
    assert all(row.status == ArtefactStatus.SUCCEEDED for row in rows)
    assert all(row.content == SVG for row in rows)
    assert all(row.source for row in rows)


async def test_duration_and_cost_are_recorded(session_factory, seeded) -> None:
    await execute_run(seeded, renderer(), session_factory=session_factory)
    run = await _run_row(session_factory, seeded)

    assert run.duration_ms is not None and run.duration_ms >= 0
    assert run.completed_at is not None
    # "0" not None: C-3 keeps the LLM out of the render path, so zero here is a
    # measurement rather than a missing number (NFR-M3).
    assert run.llm_cost_usd == "0"
    assert run.llm_input_tokens == 0 and run.llm_output_tokens == 0


# --------------------------------------------------------------------------
# NFR-R3: retrying must not duplicate
# --------------------------------------------------------------------------


async def test_retrying_an_interrupted_run_does_not_duplicate_artefacts(
    session_factory, seeded
) -> None:
    await execute_run(seeded, renderer(), session_factory=session_factory)
    # A worker that died mid-run leaves the row RUNNING with artefacts already
    # written. arq will hand the job to another worker.
    await _force_status(session_factory, seeded, RunStatus.RUNNING)
    await execute_run(seeded, renderer(), session_factory=session_factory)
    await _force_status(session_factory, seeded, RunStatus.RUNNING)
    await execute_run(seeded, renderer(), session_factory=session_factory)

    rows = await artefacts_of(seeded, session_factory=session_factory)
    run = await _run_row(session_factory, seeded)

    assert len(rows) == len(registry()), "a retry appended instead of overwriting"
    assert len({row.diagram_type for row in rows}) == len(registry())
    assert run.attempts == 3
    assert run.status == RunStatus.SUCCEEDED


async def test_the_unique_constraint_is_what_stops_the_duplicate(session_factory, seeded) -> None:
    # Otherwise the test above could pass because of an accidental id collision
    # rather than the constraint the guarantee is actually resting on.
    async with session_factory() as session:
        constraints = await session.scalars(
            text(
                "SELECT conname FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                f"WHERE n.nspname = '{SCHEMA}' AND t.relname = 'generation_artefacts' "
                "AND c.contype = 'u'"
            )
        )
        assert "uq_run_artefact" in set(constraints)


async def test_a_succeeded_run_is_not_re_executed(session_factory, seeded) -> None:
    await execute_run(seeded, renderer(), session_factory=session_factory)
    before = {
        row.diagram_type: row.updated_at for row in await artefacts_of(seeded, session_factory)
    }

    watchful = renderer()
    outcome = await execute_run(seeded, watchful, session_factory=session_factory)
    after = {
        row.diagram_type: row.updated_at for row in await artefacts_of(seeded, session_factory)
    }

    assert outcome.status == RunStatus.SUCCEEDED
    assert all(engine.calls == 0 for engine in watchful._engines.values()), (
        "a completed run re-rendered, rewriting artefacts the user may be reading"
    )
    assert after == before


# --------------------------------------------------------------------------
# Failure modes
# --------------------------------------------------------------------------


async def test_a_consistency_violation_fails_the_run(session_factory, seeded) -> None:
    original = registry()["class"]
    corrupted = DiagramMapper(
        diagram_type=original.diagram_type,
        title=original.title,
        engine=original.engine,
        to_source=lambda cpm: original.to_source(cpm).replace('"Book"', '"Books"'),
    )

    outcome = await execute_run(
        seeded,
        renderer(mappers={**registry(), "class": corrupted}),
        session_factory=session_factory,
    )
    run = await _run_row(session_factory, seeded)
    rows = await artefacts_of(seeded, session_factory=session_factory)

    assert outcome.status == RunStatus.FAILED
    assert run.status == RunStatus.FAILED
    assert "Books" in (run.error or "")
    # The artefacts stay: a failed run the user can inspect beats one that
    # vanishes, and every diagram did in fact render.
    assert len(rows) == len(registry())


async def test_a_dead_engine_costs_one_diagram_not_the_run(session_factory, seeded) -> None:
    mermaid_types = {t for t, m in registry().items() if str(m.engine) == "mermaid"}
    broken = DiagramRenderer(
        engines={"plantuml": AlwaysRenders("plantuml"), "mermaid": AlwaysFails("mermaid")}
    )

    outcome = await execute_run(seeded, broken, session_factory=session_factory)
    rows = {row.diagram_type: row for row in await artefacts_of(seeded, session_factory)}

    assert outcome.status == RunStatus.SUCCEEDED  # NFR-R2
    assert outcome.failed == len(mermaid_types)
    for diagram_type in mermaid_types:
        assert rows[diagram_type].status == ArtefactStatus.FAILED
        assert rows[diagram_type].error
    for diagram_type in set(registry()) - mermaid_types:
        assert rows[diagram_type].status == ArtefactStatus.SUCCEEDED


async def test_an_undescribed_diagram_is_skipped_not_failed(session_factory, seeded) -> None:
    original = registry()["class"]

    def refuses(cpm):
        raise InsufficientModelData("the model describes no classes")

    silent = DiagramMapper(
        diagram_type=original.diagram_type,
        title=original.title,
        engine=original.engine,
        to_source=refuses,
    )

    outcome = await execute_run(
        seeded,
        renderer(mappers={**registry(), "class": silent}),
        session_factory=session_factory,
    )
    rows = {row.diagram_type: row for row in await artefacts_of(seeded, session_factory)}

    assert outcome.status == RunStatus.SUCCEEDED
    assert outcome.skipped == 1 and outcome.failed == 0
    assert rows["class"].status == ArtefactStatus.SKIPPED
    assert "no classes" in rows["class"].error
    assert rows["class"].content is None


async def test_an_unknown_run_raises_rather_than_writing_anything(session_factory) -> None:
    with pytest.raises(RunNotFound):
        await execute_run("run_does_not_exist", renderer(), session_factory=session_factory)


async def test_a_run_pointing_at_a_missing_version_raises(session_factory) -> None:
    async with session_factory() as session:
        session.add(
            GenerationRunRow(
                id="run_orphan",
                project_id="proj_test",
                cpm_version_id="ver_gone",
                requested_types=["class"],
                fmt="svg",
                status=RunStatus.PENDING,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    with pytest.raises(RunNotFound):
        await execute_run("run_orphan", renderer(), session_factory=session_factory)


async def test_artefacts_are_marked_running_before_any_render_finishes(
    session_factory, seeded
) -> None:
    # The progress stream is only honest if the rows exist before the work does.
    seen: list[str] = []

    class Watcher(AlwaysRenders):
        async def render(self, source: str, fmt: RenderFormat) -> bytes:
            async with session_factory() as session:
                rows = await session.scalars(
                    select(GenerationRunRow).where(GenerationRunRow.id == seeded)
                )
                seen.append(list(rows)[0].status)
            return await super().render(source, fmt)

    await execute_run(
        seeded,
        DiagramRenderer(engines={"plantuml": Watcher("plantuml"), "mermaid": Watcher("mermaid")}),
        session_factory=session_factory,
    )

    assert seen and all(status == RunStatus.RUNNING for status in seen)

    async with session_factory() as session:
        rows = await session.scalars(text(f"SELECT status FROM {SCHEMA}.generation_artefacts"))
        assert set(rows) == {ArtefactStatus.SUCCEEDED.value}
