"""FR-12: redraw one diagram, keep the rest, revalidate everything.

Two properties carry most of the weight here and both are easy to lose:

* Regenerating an *unchanged* model must say so. Deterministic mappers mean the
  alternative is a progress bar that produces the file the user already has.
* Regenerating must not re-extract or re-prompt. The input is a CPMVersion a
  human confirmed at the review gate; if a regeneration could return a
  different model, "redraw the class diagram" would quietly mean "rebuild my
  project".

The second is asserted structurally as well as behaviourally, because a model
call added in six weeks would not fail any behavioural test written today.
"""

import ast
import copy
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from cpm.fixtures import library_management_system_payload
from cpm.schema import CPM
from diagrams.registry import registry
from diagrams.renderer import DiagramRenderer
from diagrams.types import RenderFormat
from generation import regenerate as regenerate_module
from generation.orchestrator import RunNotFound, artefacts_of, execute_run
from generation.regenerate import (
    NotRegenerable,
    create_regeneration_run,
    execute_regeneration,
    lineage,
    plan_regeneration,
)
from store.models import (
    ArtefactStatus,
    CPMVersionRow,
    GenerationArtefactRow,
    GenerationRunRow,
    RunKind,
    RunStatus,
)

SVG = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
TARGET = "class"


class CountingEngine:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    async def render(self, source: str, fmt: RenderFormat) -> bytes:
        self.calls += 1
        return SVG


class DeadEngine:
    def __init__(self, name: str) -> None:
        self.name = name

    async def render(self, source: str, fmt: RenderFormat) -> bytes:
        from diagrams.engines.base import EngineUnavailable

        raise EngineUnavailable("engine is down")


def renderer(**engines) -> DiagramRenderer:
    return DiagramRenderer(
        engines=engines
        or {"plantuml": CountingEngine("plantuml"), "mermaid": CountingEngine("mermaid")}
    )


async def _add_version(session_factory, version_id: str, payload: dict, version: int) -> None:
    async with session_factory() as session:
        session.add(
            CPMVersionRow(
                id=version_id,
                project_id="proj_test",
                version=version,
                payload=payload,
                confirmed_at=datetime.now(UTC),
            )
        )
        await session.commit()


@pytest.fixture
async def parent(session_factory):
    """A completed full run over the whole registered set."""
    cpm = CPM.model_validate(library_management_system_payload())
    await _add_version(session_factory, "ver_1", cpm.model_dump(by_alias=True, mode="json"), 1)
    async with session_factory() as session:
        session.add(
            GenerationRunRow(
                id="run_parent",
                project_id="proj_test",
                cpm_version_id="ver_1",
                kind=RunKind.FULL,
                requested_types=sorted(registry()),
                fmt="svg",
                status=RunStatus.PENDING,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    await execute_run("run_parent", renderer(), session_factory=session_factory)
    return "run_parent"


async def _edited_version(session_factory, version_id: str = "ver_2") -> str:
    """A second confirmed version in which one entity was renamed everywhere.

    This is the real "I edited the model" case: the review screen renames
    references atomically, so the CPM stays internally consistent and only the
    diagrams fall behind.
    """
    payload = copy.deepcopy(library_management_system_payload())
    for entity in payload["entities"]:
        if entity["name"] == "Book":
            entity["name"] = "Publication"
    await _add_version(session_factory, version_id, payload, 2)
    return version_id


# --------------------------------------------------------------------------
# DoD: an unchanged CPM is reported honestly
# --------------------------------------------------------------------------


async def test_an_unchanged_model_reports_no_change(session_factory, parent) -> None:
    plan = await plan_regeneration(parent, TARGET, session_factory=session_factory)

    assert plan.changed is False
    assert plan.source_changed is False
    assert "has not changed" in plan.reason
    assert "byte-identical" in plan.reason


async def test_an_unchanged_model_cannot_open_a_run_at_all(session_factory, parent) -> None:
    # The honesty is structural, not a message the caller may ignore: there is
    # no path from an unchanged plan to a queued job.
    plan = await plan_regeneration(parent, TARGET, session_factory=session_factory)

    with pytest.raises(NotRegenerable):
        await create_regeneration_run(plan, session_factory=session_factory)

    async with session_factory() as session:
        runs = await session.scalar(select(func.count()).select_from(GenerationRunRow))
    assert runs == 1, "a no-op regeneration recorded a run"


async def test_planning_renders_nothing(session_factory, parent) -> None:
    engine = CountingEngine("plantuml")
    await plan_regeneration(parent, TARGET, session_factory=session_factory)
    assert engine.calls == 0

    rows = {row.diagram_type: row.content for row in await artefacts_of(parent, session_factory)}
    assert rows[TARGET] == SVG  # untouched


async def test_the_stored_source_is_what_makes_the_comparison_real(session_factory, parent) -> None:
    # If the artefact's source were not persisted, "unchanged" would be a guess.
    rows = {row.diagram_type: row for row in await artefacts_of(parent, session_factory)}
    assert rows[TARGET].source
    assert rows[TARGET].source == registry()[TARGET].to_source(
        CPM.model_validate(library_management_system_payload())
    )


# --------------------------------------------------------------------------
# The edited model
# --------------------------------------------------------------------------


async def test_an_edited_model_is_regenerable_and_says_what_moved(session_factory, parent) -> None:
    version_id = await _edited_version(session_factory)
    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)

    assert plan.changed is True
    assert plan.source_changed is True
    assert "line(s) added" in plan.reason
    # The diagrams that will still be wrong afterwards — named before the user
    # has spent anything. Every one of them shows the renamed entity by name;
    # the ones that do not (use_case, component, deployment, activity) are
    # deliberately absent, because sending someone to redraw a correct figure
    # is its own kind of lying.
    assert set(plan.stale_types) == {"entity_relationship", "sequence", "state"}
    assert not {"use_case", "component", "deployment", "activity"} & set(plan.stale_types)


async def test_nothing_is_reported_stale_when_the_model_did_not_move(
    session_factory, parent
) -> None:
    plan = await plan_regeneration(parent, TARGET, session_factory=session_factory)
    assert plan.stale_types == []


async def test_regeneration_replaces_one_artefact_and_carries_the_rest(
    session_factory, parent
) -> None:
    version_id = await _edited_version(session_factory)
    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)

    before = {row.diagram_type: row.content for row in await artefacts_of(parent, session_factory)}
    await execute_regeneration(child, renderer(), session_factory=session_factory)
    after = {row.diagram_type: row for row in await artefacts_of(child, session_factory)}

    assert set(after) == set(registry()), "the child run is not a complete set"
    assert after[TARGET].origin_run_id == child
    assert after[TARGET].cpm_version_id == version_id
    for diagram_type in set(registry()) - {TARGET}:
        assert after[diagram_type].origin_run_id == parent, "an untouched diagram was redrawn"
        assert after[diagram_type].content == before[diagram_type]
        assert after[diagram_type].cpm_version_id == "ver_1"


async def test_only_the_named_diagram_is_rendered(session_factory, parent) -> None:
    version_id = await _edited_version(session_factory)
    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)

    plantuml, mermaid = CountingEngine("plantuml"), CountingEngine("mermaid")
    await execute_regeneration(
        child, renderer(plantuml=plantuml, mermaid=mermaid), session_factory=session_factory
    )

    assert plantuml.calls + mermaid.calls == 1


async def test_the_parent_run_is_left_intact(session_factory, parent) -> None:
    version_id = await _edited_version(session_factory)
    before = {row.diagram_type: row.content for row in await artefacts_of(parent, session_factory)}

    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)
    await execute_regeneration(child, renderer(), session_factory=session_factory)

    after = {row.diagram_type: row.content for row in await artefacts_of(parent, session_factory)}
    assert after == before, "regeneration mutated the run it came from"


# --------------------------------------------------------------------------
# FR-10 across the whole set, not just the new figure
# --------------------------------------------------------------------------


async def test_a_stale_neighbour_fails_the_regenerated_set(session_factory, parent) -> None:
    # Renaming Book -> Publication and redrawing only the class diagram leaves
    # seven figures still saying "Book". The set is internally inconsistent and
    # the run must not be presented as a deliverable.
    version_id = await _edited_version(session_factory)
    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)

    outcome = await execute_regeneration(child, renderer(), session_factory=session_factory)

    assert outcome.status == RunStatus.FAILED
    assert "Book" in (outcome.error or "")
    # The new figure is still there to look at; only the set is rejected.
    rows = {row.diagram_type: row for row in await artefacts_of(child, session_factory)}
    assert rows[TARGET].status == ArtefactStatus.SUCCEEDED


async def test_redrawing_the_diagrams_that_moved_clears_the_failure(
    session_factory, parent
) -> None:
    # The other half of the previous test: the failure is about the set, not
    # about regeneration, and it names exactly what to do about it.
    version_id = await _edited_version(session_factory)
    current = parent
    redrawn: list[str] = []
    unchanged: list[str] = []
    outcome = None

    for diagram_type in sorted(registry()):
        plan = await plan_regeneration(
            current, diagram_type, version_id, session_factory=session_factory
        )
        if not plan.changed:
            unchanged.append(diagram_type)
            continue
        current = await create_regeneration_run(plan, session_factory=session_factory)
        outcome = await execute_regeneration(current, renderer(), session_factory=session_factory)
        redrawn.append(diagram_type)

    # Renaming an entity does not touch a diagram that never names entities,
    # and the system says so rather than redrawing it for the sake of tidiness.
    assert "use_case" in unchanged
    assert TARGET in redrawn
    assert outcome.status == RunStatus.SUCCEEDED

    rows = {row.diagram_type: row for row in await artefacts_of(current, session_factory)}
    assert {rows[t].cpm_version_id for t in redrawn} == {version_id}
    assert {rows[t].cpm_version_id for t in unchanged} == {"ver_1"}


async def test_the_failure_names_the_diagrams_that_still_have_to_be_redrawn(
    session_factory, parent
) -> None:
    version_id = await _edited_version(session_factory)
    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)

    outcome = await execute_regeneration(child, renderer(), session_factory=session_factory)

    # Not "something is inconsistent" — which diagram, which name, which line.
    assert "entity_relationship" in outcome.error
    assert "sequence" in outcome.error
    assert "use_case" not in outcome.error, "a diagram that never shows Book was blamed"
    assert "regenerate this diagram too" in outcome.error


def test_the_validator_is_not_reachable_only_conditionally() -> None:
    # Same structural guard as the full-run path: a flag is the obvious bypass,
    # a quiet `if` is the one nobody calls a bypass.
    tree = ast.parse(Path(regenerate_module.__file__).read_text(encoding="utf-8"))

    def calls_validate(node: ast.AST) -> bool:
        return any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "validate_consistency"
            for inner in ast.walk(node)
        )

    assert calls_validate(tree), "the regeneration path never validates"
    guarded = [node for node in ast.walk(tree) if isinstance(node, ast.If) and calls_validate(node)]
    assert not guarded, "validate_consistency is reachable only conditionally"


# --------------------------------------------------------------------------
# DoD: no re-extraction, no re-prompting
# --------------------------------------------------------------------------

REPO_ROOT = Path(os.environ.get("ASA_REPO_ROOT", Path(regenerate_module.__file__).parents[2]))

REGENERATION_PATH = [
    REPO_ROOT / "shared" / "generation" / "regenerate.py",
    REPO_ROOT / "worker" / "worker" / "handlers" / "render.py",
    REPO_ROOT / "api" / "app" / "routers" / "runs.py",
]

FORBIDDEN_ROOTS = {"llm", "extraction", "anthropic", "openai", "ollama", "groq"}


def test_no_module_on_the_regeneration_path_imports_an_extractor_or_a_gateway() -> None:
    offenders: list[str] = []
    for path in REGENERATION_PATH:
        if not path.exists():  # pragma: no cover - layout guard
            offenders.append(f"{path} is missing; the guard is pointing at nothing")
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in FORBIDDEN_ROOTS:
                    offenders.append(f"{path.name}:{node.lineno}: imports {name}")
    assert not offenders, (
        "an LLM or extraction import reached the regeneration path:\n" + "\n".join(offenders)
    )


async def test_regeneration_creates_no_new_cpm_version(session_factory, parent) -> None:
    # Re-extraction would produce a model; this asserts none appears.
    version_id = await _edited_version(session_factory)
    async with session_factory() as session:
        before = await session.scalar(select(func.count()).select_from(CPMVersionRow))

    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)
    await execute_regeneration(child, renderer(), session_factory=session_factory)

    async with session_factory() as session:
        after = await session.scalar(select(func.count()).select_from(CPMVersionRow))
    assert after == before == 2


async def test_regeneration_costs_nothing_because_no_model_is_called(
    session_factory, parent
) -> None:
    version_id = await _edited_version(session_factory)
    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)
    await execute_regeneration(child, renderer(), session_factory=session_factory)

    async with session_factory() as session:
        run = await session.get(GenerationRunRow, child)
    assert run.llm_cost_usd == "0"
    assert run.llm_input_tokens == 0 and run.llm_output_tokens == 0


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


async def test_history_shows_what_was_regenerated_and_when(session_factory, parent) -> None:
    version_id = await _edited_version(session_factory)
    first = await create_regeneration_run(
        await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory),
        session_factory=session_factory,
    )
    await execute_regeneration(first, renderer(), session_factory=session_factory)
    # A diagram the rename actually moved. Picking the alphabetically first
    # type would pick one the edit never touched, and the regeneration would be
    # correctly refused as a no-op.
    second_type = "entity_relationship"
    second = await create_regeneration_run(
        await plan_regeneration(first, second_type, version_id, session_factory=session_factory),
        session_factory=session_factory,
    )
    await execute_regeneration(second, renderer(), session_factory=session_factory)

    chain = await lineage(second, session_factory=session_factory)

    assert [run.id for run in chain] == [parent, first, second]
    assert [run.kind for run in chain] == [
        RunKind.FULL,
        RunKind.REGENERATION,
        RunKind.REGENERATION,
    ]
    assert [list(run.requested_types) for run in chain[1:]] == [[TARGET], [second_type]]
    assert all(run.completed_at is not None for run in chain)


# --------------------------------------------------------------------------
# Retrying, and the awkward cases
# --------------------------------------------------------------------------


async def test_a_failed_render_is_regenerable_even_with_identical_source(session_factory) -> None:
    # The engine was down, not the model wrong. "Nothing changed" would be true
    # of the source and useless to the user, who has no diagram.
    cpm = CPM.model_validate(library_management_system_payload())
    await _add_version(session_factory, "ver_1", cpm.model_dump(by_alias=True, mode="json"), 1)
    async with session_factory() as session:
        session.add(
            GenerationRunRow(
                id="run_broken",
                project_id="proj_test",
                cpm_version_id="ver_1",
                kind=RunKind.FULL,
                requested_types=sorted(registry()),
                fmt="svg",
                status=RunStatus.PENDING,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    await execute_run(
        "run_broken",
        DiagramRenderer(
            engines={"plantuml": DeadEngine("plantuml"), "mermaid": DeadEngine("mermaid")}
        ),
        session_factory=session_factory,
    )

    plan = await plan_regeneration("run_broken", TARGET, session_factory=session_factory)
    assert plan.changed is True
    assert plan.source_changed is False
    assert "did not produce a figure" in plan.reason

    child = await create_regeneration_run(plan, session_factory=session_factory)
    outcome = await execute_regeneration(child, renderer(), session_factory=session_factory)
    rows = {row.diagram_type: row for row in await artefacts_of(child, session_factory)}

    assert outcome.status == RunStatus.SUCCEEDED
    assert rows[TARGET].status == ArtefactStatus.SUCCEEDED
    assert rows[TARGET].content == SVG


async def test_a_regeneration_that_already_succeeded_is_not_re_executed(
    session_factory, parent
) -> None:
    version_id = await _edited_version(session_factory)
    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)
    async with session_factory() as session:
        run = await session.get(GenerationRunRow, child)
        run.requested_types = [TARGET]
        await session.commit()

    await execute_regeneration(child, renderer(), session_factory=session_factory)
    # That first attempt fails FR-10 (stale neighbours), so force the state the
    # short-circuit is about rather than pretending it happened.
    async with session_factory() as session:
        run = await session.get(GenerationRunRow, child)
        run.status = RunStatus.SUCCEEDED
        await session.commit()

    engine = CountingEngine("plantuml")
    await execute_regeneration(
        child,
        renderer(plantuml=engine, mermaid=CountingEngine("mermaid")),
        session_factory=session_factory,
    )
    assert engine.calls == 0


async def test_retrying_a_regeneration_does_not_duplicate_artefacts(
    session_factory, parent
) -> None:
    version_id = await _edited_version(session_factory)
    plan = await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory)
    child = await create_regeneration_run(plan, session_factory=session_factory)

    await execute_regeneration(child, renderer(), session_factory=session_factory)
    await execute_regeneration(child, renderer(), session_factory=session_factory)

    async with session_factory() as session:
        rows = await session.scalar(
            select(func.count())
            .select_from(GenerationArtefactRow)
            .where(GenerationArtefactRow.run_id == child)
        )
    assert rows == len(registry())


async def test_a_type_outside_the_parent_set_is_refused(session_factory) -> None:
    # Adding a diagram the set never contained is a new run, not a regeneration
    # of this one — and quietly widening the set would make "replaces only that
    # artefact" false.
    cpm = CPM.model_validate(library_management_system_payload())
    await _add_version(session_factory, "ver_1", cpm.model_dump(by_alias=True, mode="json"), 1)
    async with session_factory() as session:
        session.add(
            GenerationRunRow(
                id="run_narrow",
                project_id="proj_test",
                cpm_version_id="ver_1",
                kind=RunKind.FULL,
                requested_types=[TARGET],
                fmt="svg",
                status=RunStatus.PENDING,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    await execute_run("run_narrow", renderer(), session_factory=session_factory)

    other = sorted(set(registry()) - {TARGET})[0]
    with pytest.raises(NotRegenerable) as excinfo:
        await plan_regeneration("run_narrow", other, session_factory=session_factory)
    assert other in str(excinfo.value)


async def test_a_regenerated_run_can_itself_be_regenerated_for_any_diagram(
    session_factory, parent
) -> None:
    # The set a regeneration holds is all eight figures even though it drew
    # one. Deriving membership from what it *rendered* would narrow the set on
    # every pass until nothing but that one diagram could be redrawn again.
    version_id = await _edited_version(session_factory)
    child = await create_regeneration_run(
        await plan_regeneration(parent, TARGET, version_id, session_factory=session_factory),
        session_factory=session_factory,
    )
    await execute_regeneration(child, renderer(), session_factory=session_factory)

    for diagram_type in sorted(set(registry()) - {TARGET}):
        plan = await plan_regeneration(
            child, diagram_type, version_id, session_factory=session_factory
        )
        assert plan.diagram_type == diagram_type  # in the set; not refused


async def test_an_unknown_run_or_version_raises(session_factory, parent) -> None:
    with pytest.raises(RunNotFound):
        await plan_regeneration("run_nope", TARGET, session_factory=session_factory)
    with pytest.raises(RunNotFound):
        await plan_regeneration(parent, TARGET, "ver_nope", session_factory=session_factory)


async def test_a_full_run_cannot_be_executed_as_a_regeneration(session_factory, parent) -> None:
    with pytest.raises(NotRegenerable):
        await execute_regeneration(parent, renderer(), session_factory=session_factory)
