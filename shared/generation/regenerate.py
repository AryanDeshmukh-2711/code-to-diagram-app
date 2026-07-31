"""FR-12: redraw one diagram without redrawing the set.

The honest framing of this feature is "re-render after I edited the model",
not "try again and hope for a better picture". Mappers are pure and
deterministic (FR-9), so the same CPM through the same mapper produces the same
bytes — asking for a regeneration of an unmodified model can only ever hand
back the file the user already has. Doing that silently, behind a progress bar,
would teach them that the button does something when it does not.

So the decision comes first and the work comes second:

    plan_regeneration()   read the model, run the mapper, compare the source
    execute_regeneration()  only if the source actually differs

The mapper is a pure function over an already-confirmed CPMVersion, costing
under a millisecond and touching no network, which is why planning can answer
the user in the request cycle without breaking C-4. Nothing is rendered,
stored, extracted or prompted there.

Never re-extract, never re-prompt: the input is a CPMVersion row that a human
already confirmed at the review gate (FR-6). A regeneration that re-ran the
model could return a *different* model, which would make "regenerate the class
diagram" quietly mean "rebuild my project", and would put an LLM call in a path
the user thinks is deterministic. This module imports no extractor and no
gateway, and a test asserts that it stays that way.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select

from consistency.validator import (
    ConsistencyReport,
    ConsistencyViolation,
    cpm_display_names,
    validate_consistency,
    validate_stale_names,
)
from cpm.schema import CPM
from diagrams.mapper import InsufficientModelData
from diagrams.registry import get_mapper
from diagrams.renderer import DiagramRenderer
from diagrams.types import RenderFormat, SkippedDiagram
from generation.orchestrator import (
    RunNotFound,
    artefact_id,
    artefact_values,
    finalise_run,
    upsert_artefact,
)
from store.models import (
    ArtefactStatus,
    CPMVersionRow,
    GenerationArtefactRow,
    GenerationRunRow,
    RunKind,
    RunStatus,
)
from store.session import SessionFactory

logger = logging.getLogger(__name__)


class NotRegenerable(ValueError):
    """The request cannot be honoured as a regeneration of that run."""


@dataclass(frozen=True)
class RegenerationPlan:
    """What would happen, decided before anything is rendered."""

    parent_run_id: str
    project_id: str
    diagram_type: str
    cpm_version_id: str
    fmt: str
    changed: bool
    reason: str
    previous_status: str | None = None
    source_changed: bool = False
    stale_types: list[str] = field(default_factory=list)
    """Other diagrams in the set that will still contradict the model after
    this one is redrawn — each one shows a name the target version no longer
    has. Not a blocker; the validator decides the run. But telling a student up
    front which figures still need attention is the difference between one
    informed pass and four confused ones."""


def _describe_source_change(previous: str | None, current: str) -> str:
    if not previous:
        return "no previous source was stored for this diagram"
    before = previous.splitlines()
    after = current.splitlines()
    added = len([line for line in after if line not in before])
    removed = len([line for line in before if line not in after])
    return f"the model changed: {added} line(s) added, {removed} removed in the diagram source"


async def plan_regeneration(
    parent_run_id: str,
    diagram_type: str,
    cpm_version_id: str | None = None,
    session_factory=SessionFactory,
) -> RegenerationPlan:
    """Decide whether regenerating would produce anything new.

    Reads; does not write, render, extract or prompt.
    """
    async with session_factory() as session:
        parent = await session.get(GenerationRunRow, parent_run_id)
        if parent is None:
            raise RunNotFound(f"no generation run {parent_run_id!r}")

        rows = list(
            await session.scalars(
                select(GenerationArtefactRow).where(GenerationArtefactRow.run_id == parent_run_id)
            )
        )
        # The set is what the run *holds*, not what it drew: a regeneration
        # renders one diagram and carries seven, and all eight are regenerable
        # from it. Using requested_types here would make each regeneration
        # narrow the set until only one diagram could ever be redrawn again.
        contains = {row.diagram_type for row in rows} or set(parent.requested_types)
        if diagram_type not in contains:
            # Adding a diagram type that was never part of this set is a new
            # run, not a regeneration of this one.
            raise NotRegenerable(
                f"{diagram_type!r} is not part of run {parent_run_id!r}; "
                f"it contains {', '.join(sorted(contains))}"
            )

        target_version_id = cpm_version_id or parent.cpm_version_id
        version = await session.get(CPMVersionRow, target_version_id)
        if version is None:
            raise RunNotFound(f"no confirmed CPM version {target_version_id!r}")
        if version.project_id != parent.project_id:
            raise NotRegenerable(
                f"CPM version {target_version_id!r} belongs to a different project"
            )

        previous = await session.get(
            GenerationArtefactRow, artefact_id(parent_run_id, diagram_type, parent.fmt)
        )
        previous_names = await _names_by_version(session, rows, target_version_id)

    cpm = CPM.model_validate(version.payload)

    # Not "which figures are older" — which ones will still be *wrong* once
    # this one is redrawn. A use case diagram is untouched by renaming an
    # entity, and listing it would send a student to redraw a correct figure.
    neighbours = [row for row in rows if row.diagram_type != diagram_type]
    stale = sorted(
        {v.diagram_type for v in validate_stale_names(cpm, neighbours, previous_names).violations}
    )

    try:
        source = get_mapper(diagram_type).to_source(cpm)
    except InsufficientModelData as exc:
        source = ""
        reason_if_same = f"the model still does not describe this diagram: {exc.reason}"
    else:
        reason_if_same = (
            "the model has not changed since this diagram was drawn, and the "
            "renderer is deterministic — regenerating would produce a "
            "byte-identical file"
        )

    previous_status = previous.status if previous else None
    previous_source = previous.source if previous else None
    source_changed = (previous_source or "") != source

    if source_changed:
        changed, reason = True, _describe_source_change(previous_source, source)
    elif previous_status not in (ArtefactStatus.SUCCEEDED, ArtefactStatus.SKIPPED):
        # Identical source, but there is no usable artefact — the engine was
        # down, or the run was interrupted. Re-rendering is genuinely useful.
        changed = True
        reason = (
            "the diagram source is unchanged, but the last attempt did not "
            f"produce a figure ({previous_status or 'never rendered'})"
        )
    else:
        changed, reason = False, reason_if_same

    return RegenerationPlan(
        parent_run_id=parent_run_id,
        project_id=parent.project_id,
        diagram_type=diagram_type,
        cpm_version_id=target_version_id,
        fmt=parent.fmt,
        changed=changed,
        reason=reason,
        previous_status=previous_status,
        source_changed=source_changed,
        stale_types=stale,
    )


async def _names_by_version(session, rows, target_version_id: str) -> dict[str, set[str]]:
    """For each carried-forward artefact, the names its own model version had.

    Only artefacts drawn from a different version are loaded — a set that is
    entirely current has nothing to be stale against, and pays nothing.
    """
    wanted = {
        row.cpm_version_id
        for row in rows
        if row.cpm_version_id and row.cpm_version_id != target_version_id
    }
    if not wanted:
        return {}

    versions = await session.scalars(
        select(CPMVersionRow).where(CPMVersionRow.id.in_(sorted(wanted)))
    )
    names = {
        version.id: cpm_display_names(CPM.model_validate(version.payload)) for version in versions
    }
    return {
        row.diagram_type: names[row.cpm_version_id] for row in rows if row.cpm_version_id in names
    }


async def create_regeneration_run(
    plan: RegenerationPlan,
    template_id: str | None = None,
    session_factory=SessionFactory,
) -> str:
    """Open a child run for a plan that has something to do.

    Refuses an unchanged plan rather than recording a run that redraws nothing.
    A history of non-events is worse than no history: it makes "what was
    regenerated and when" unanswerable by listing everything the user clicked.
    """
    if not plan.changed:
        raise NotRegenerable(f"nothing to regenerate for {plan.diagram_type!r}: {plan.reason}")

    import uuid

    run_id = f"run_{uuid.uuid4().hex[:16]}"
    async with session_factory() as session:
        session.add(
            GenerationRunRow(
                id=run_id,
                project_id=plan.project_id,
                cpm_version_id=plan.cpm_version_id,
                template_id=template_id,
                kind=RunKind.REGENERATION,
                parent_run_id=plan.parent_run_id,
                requested_types=[plan.diagram_type],
                fmt=plan.fmt,
                status=RunStatus.PENDING,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    return run_id


async def execute_regeneration(
    run_id: str,
    renderer: DiagramRenderer,
    session_factory=SessionFactory,
):
    """Render the one diagram this run asks for, carry the rest forward, and
    validate the whole set.

    The carry-forward is what makes the result a complete deliverable rather
    than a fragment: a run is the unit a user exports, so a regeneration has to
    end up holding all eight figures even though it drew one.
    """
    from generation.orchestrator import RunOutcome  # local: avoids a cycle at import

    started = datetime.now(UTC)

    async with session_factory() as session:
        run = await session.get(GenerationRunRow, run_id)
        if run is None:
            raise RunNotFound(f"no generation run {run_id!r}")
        if run.kind != RunKind.REGENERATION or not run.parent_run_id:
            raise NotRegenerable(f"run {run_id!r} is not a regeneration")

        if run.status == RunStatus.SUCCEEDED:
            return RunOutcome(
                run_id=run_id,
                status=run.status,
                duration_ms=run.duration_ms or 0,
                succeeded=0,
                failed=0,
                skipped=0,
                llm_cost_usd=run.llm_cost_usd,
            )

        version = await session.get(CPMVersionRow, run.cpm_version_id)
        if version is None:
            raise RunNotFound(f"run {run_id!r} references missing CPM version")

        parent_id = run.parent_run_id
        fmt = RenderFormat(run.fmt)
        targets = list(run.requested_types)
        version_id = run.cpm_version_id

        run.status = RunStatus.RUNNING
        run.started_at = started
        run.attempts += 1
        run.error = None

        inherited = await session.scalars(
            select(GenerationArtefactRow).where(GenerationArtefactRow.run_id == parent_id)
        )
        for row in inherited:
            if row.diagram_type in targets:
                continue
            # Same bytes, new run. The provenance columns are what keep this
            # from looking like eight fresh renders.
            await upsert_artefact(
                session,
                run_id,
                fmt.value,
                {
                    "id": artefact_id(run_id, row.diagram_type, fmt.value),
                    "run_id": run_id,
                    "diagram_type": row.diagram_type,
                    "format": fmt.value,
                    "status": row.status,
                    "title": row.title,
                    "engine": row.engine,
                    "source": row.source,
                    "content": row.content,
                    "error": row.error,
                    "attempts": row.attempts,
                    "cpm_version_id": row.cpm_version_id,
                    "origin_run_id": row.origin_run_id or parent_id,
                },
            )

        for diagram_type in targets:
            await upsert_artefact(
                session,
                run_id,
                fmt.value,
                {
                    "id": artefact_id(run_id, diagram_type, fmt.value),
                    "run_id": run_id,
                    "diagram_type": diagram_type,
                    "format": fmt.value,
                    "status": ArtefactStatus.RUNNING,
                    "error": None,
                    "cpm_version_id": version_id,
                    "origin_run_id": run_id,
                },
            )
        await session.commit()

    cpm = CPM.model_validate(version.payload)

    status = RunStatus.SUCCEEDED
    error: str | None = None
    counts = {"succeeded": 0, "failed": 0, "skipped": 0}

    try:
        for diagram_type in targets:
            result = await renderer.render(cpm, diagram_type, fmt)
            async with session_factory() as session:
                await upsert_artefact(
                    session,
                    run_id,
                    fmt.value,
                    artefact_values(run_id, fmt.value, result, version_id, run_id),
                )
                await session.commit()
            if result.ok:
                counts["succeeded"] += 1
            elif isinstance(result, SkippedDiagram):
                counts["skipped"] += 1
            else:
                counts["failed"] += 1

        # FR-12: the whole set, not the one diagram. Replacing one figure can
        # only be safe if the other seven still agree with the model, and after
        # an edit to the CPM they may not.
        async with session_factory() as session:
            rows = list(
                await session.scalars(
                    select(GenerationArtefactRow)
                    .where(GenerationArtefactRow.run_id == run_id)
                    .order_by(GenerationArtefactRow.diagram_type)
                )
            )
            previous_names = await _names_by_version(session, rows, version_id)

        report = validate_consistency(cpm, rows)
        stale_report = validate_stale_names(cpm, rows, previous_names)
        report = ConsistencyReport(
            violations=report.violations + stale_report.violations,
            checked_diagrams=report.checked_diagrams,
            recognised_names=report.recognised_names,
        )

        if not report.ok:
            # A replaced figure that disagrees with its seven neighbours is
            # exactly the drift FR-10 exists to stop, and it is likelier here
            # than in a full run: the neighbours were drawn earlier.
            logger.error("regeneration %s failed FR-10:\n%s", run_id, report.render())
            raise ConsistencyViolation(report)
        logger.info("%s", report.render())
    except ConsistencyViolation as exc:
        status = RunStatus.FAILED
        error = str(exc)
    except Exception as exc:
        status = RunStatus.FAILED
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("regeneration %s failed", run_id)

    # No sink: nothing on this path can call a model, so the zero is a fact
    # about the design rather than a total nobody added up.
    duration_ms, total_cost = await finalise_run(
        run_id, status, error, started, None, session_factory
    )

    return RunOutcome(
        run_id=run_id,
        status=status,
        duration_ms=duration_ms,
        succeeded=counts["succeeded"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        llm_cost_usd=None if total_cost is None else str(total_cost),
        error=error,
    )


async def lineage(run_id: str, session_factory=SessionFactory) -> list[GenerationRunRow]:
    """The run and its ancestors, oldest first — what was regenerated, when."""
    chain: list[GenerationRunRow] = []
    seen: set[str] = set()
    async with session_factory() as session:
        current: str | None = run_id
        while current and current not in seen:
            seen.add(current)
            run = await session.get(GenerationRunRow, current)
            if run is None:
                break
            chain.append(run)
            current = run.parent_run_id
    return list(reversed(chain))
