"""A generation run: render the artefact set, then check it against the CPM.

Validation is not a step you can turn off. There is no `validate` parameter, no
flag to skip it, no environment variable and no severity setting — because an
escape hatch here does not stay unused. It gets reached for at 2am when a
deadline is closer than the bug, and the guarantee the product is sold on dies
without anyone deciding to kill it.

The asymmetry with FR-11 is deliberate and worth stating. A single diagram
failing to *render* does not abort the run (NFR-R2) — the user still gets the
other seven. A *consistency* violation does abort it, because the artefacts
disagree with each other, and a set that looks complete while contradicting
itself is worse than a set that is visibly short one diagram.
"""

import logging
from dataclasses import dataclass

from consistency.validator import (
    ConsistencyReport,
    ConsistencyViolation,
    validate_consistency,
)
from cpm.schema import CPM
from diagrams.renderer import DiagramRenderer
from diagrams.types import DiagramResult, RenderFormat, SkippedDiagram

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationRunResult:
    cpm: CPM
    diagrams: list[DiagramResult]
    consistency: ConsistencyReport

    @property
    def rendered(self) -> list[DiagramResult]:
        return [diagram for diagram in self.diagrams if diagram.ok]

    @property
    def failed(self) -> list[DiagramResult]:
        """Diagrams that could not be drawn. Excludes skipped ones — a diagram
        the model never described is not a failure and must not be reported to
        the user as one."""
        return [
            diagram
            for diagram in self.diagrams
            if not diagram.ok and not isinstance(diagram, SkippedDiagram)
        ]

    @property
    def skipped(self) -> list[SkippedDiagram]:
        return [diagram for diagram in self.diagrams if isinstance(diagram, SkippedDiagram)]


async def execute_generation_run(
    cpm: CPM,
    renderer: DiagramRenderer,
    diagram_types: list[str] | None = None,
    fmt: RenderFormat = RenderFormat.SVG,
) -> GenerationRunResult:
    """Render the diagram set and validate it. Raises on a consistency violation.

    Note the parameters: there is nothing here that makes validation optional,
    and nothing should ever be added.
    """
    diagrams = await renderer.render_all(cpm, diagram_types, fmt)

    report = validate_consistency(cpm, diagrams)

    if not report.ok:
        logger.error("generation run failed FR-10 consistency:\n%s", report.render())
        raise ConsistencyViolation(report)

    logger.info("%s", report.render())
    return GenerationRunResult(cpm=cpm, diagrams=diagrams, consistency=report)
