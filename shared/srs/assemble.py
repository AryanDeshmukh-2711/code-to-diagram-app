"""Assembling the SRS: build, number, check, return.

Four steps, always in this order, with no way to ask for three of them:

1. `build_document` lays out the IEEE 830 sections from the CPM.
2. `number` assigns section, figure and table numbers and resolves every
   cross-reference, then derives the index tables from the numbered tree.
3. FR-10 runs over the prose. Every name-shaped phrase the document uses is
   checked against the CPM exactly as a diagram's source is — a section that
   says "Books" when the class diagram says "Book" is the same failure, and
   the fact that a human wrote one and a model wrote the other is irrelevant.
4. NFR-Q4 asserts that no placeholder survived.

Steps 3 and 4 are unconditional and take no parameters. That is the same
decision made for the generation run's validator and for the same reason: an
escape hatch here gets reached for at 2am, and the guarantee dies without
anyone deciding to kill it.

The result is a `Document` and nothing else. No PDF, no DOCX, no HTML — the
exporters are separate and each renders the tree directly, so neither format
is ever a translation of the other.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from consistency.names import PROSE
from consistency.validator import ConsistencyReport, ConsistencyViolation, validate_consistency
from cpm.schema import CPM
from srs.ast import Document, prose_text
from srs.ast import figures as document_figures
from srs.ast import tables as document_tables
from srs.ieee830 import FigureInput, build_document
from srs.numbering import number
from srs.placeholders import Placeholder, assert_no_placeholders
from srs.prose import DeterministicProse, ProseSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProseFragment:
    """One passage of narrative, shaped so the FR-10 validator can read it.

    `diagram_type` and `engine` are what `validate_consistency` looks for; the
    prose is handed to it under the same interface a diagram source uses, so
    there is one implementation of the guarantee rather than two.
    """

    diagram_type: str
    engine: str
    source: str


@dataclass(frozen=True)
class AssembledSRS:
    document: Document
    consistency: ConsistencyReport
    warnings: list[Placeholder]

    @property
    def figure_count(self) -> int:
        return len(document_figures(self.document))

    @property
    def table_count(self) -> int:
        return len(document_tables(self.document))


async def assemble_srs(
    cpm: CPM,
    figures: Sequence[FigureInput] = (),
    prose: ProseSource | None = None,
    *,
    cpm_version_id: str | None = None,
    run_id: str | None = None,
) -> AssembledSRS:
    """Build the SRS for one confirmed CPM.

    `prose` defaults to the deterministic writer: free, reproducible, and
    incapable of stating a requirement nobody wrote down.
    """
    document = await build_document(
        cpm,
        figures,
        prose or DeterministicProse(),
        cpm_version_id=cpm_version_id,
        run_id=run_id,
    )
    document = number(document)

    fragments = [
        ProseFragment(diagram_type=f"SRS {location}", engine=PROSE, source=text)
        for location, text in prose_text(document)
    ]
    report = validate_consistency(cpm, fragments)
    if not report.ok:
        logger.error("SRS assembly failed FR-10 consistency:\n%s", report.render())
        raise ConsistencyViolation(report)

    warnings = assert_no_placeholders(document)
    if warnings:
        logger.warning(
            "%d unfinished marker(s) carried over from the model: %s",
            len(warnings),
            ", ".join(sorted({w.token for w in warnings})),
        )

    logger.info(
        "SRS assembled: %d figures, %d tables, %s",
        len(document_figures(document)),
        len(document_tables(document)),
        report.render(),
    )
    return AssembledSRS(document=document, consistency=report, warnings=warnings)
