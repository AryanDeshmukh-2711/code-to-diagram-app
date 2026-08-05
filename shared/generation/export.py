"""Executing an export request. The worker's half of C-4.

Everything that costs time lives here: gathering the artefacts, assembling the
SRS, applying the template, rendering the file. The API's half is now three
statements — check entitlement, write the row, enqueue — which is what makes
the request return in milliseconds regardless of how long a forty-page
document takes.

Nothing about the document changed in the move. It is the same assembler, the
same template application and the same two exporters; the only difference is
which process runs them.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from cpm.schema import CPM
from srs.assemble import assemble_srs
from srs.export.docx import export_docx
from srs.export.pdf import export_pdf
from srs.ieee830 import CAPTIONS, FigureInput
from srs.template.apply import (
    MissingTemplateFields,
    TemplateInputs,
    apply_template,
    get_template,
    to_document_template,
)
from store.models import CPMVersionRow, ExportRow, GenerationArtefactRow, GenerationRunRow
from store.session import SessionFactory

logger = logging.getLogger(__name__)

MIME_OF_FORMAT = {"svg": "image/svg+xml", "png": "image/png"}


class ExportNotFound(LookupError):
    pass


@dataclass(frozen=True)
class ExportOutcome:
    export_id: str
    status: str
    format: str
    size: int
    duration_ms: int
    error: str | None = None


async def gather_figures(session, run: GenerationRunRow) -> list[FigureInput]:
    """Every rendition of this model, primary first.

    Across runs, not just this one: a project rendered as SVG and PNG can
    export either format without being told to render again.
    """
    rows = list(
        await session.scalars(
            select(GenerationArtefactRow)
            .join(GenerationRunRow, GenerationRunRow.id == GenerationArtefactRow.run_id)
            .where(
                GenerationRunRow.cpm_version_id == run.cpm_version_id,
                GenerationArtefactRow.status == "succeeded",
            )
            .order_by(GenerationArtefactRow.updated_at)
        )
    )

    by_type: dict[str, dict[str, tuple[str, bytes]]] = {}
    for row in rows:
        if row.content:
            mime = MIME_OF_FORMAT.get(row.format, "image/png")
            by_type.setdefault(row.diagram_type, {})[mime] = (row.title, row.content)

    primary = MIME_OF_FORMAT.get(run.fmt, "image/png")
    figures: list[FigureInput] = []
    for diagram_type, renditions in sorted(by_type.items()):
        mime = primary if primary in renditions else next(iter(renditions))
        title, payload = renditions[mime]
        figures.append(
            FigureInput(
                diagram_type=diagram_type,
                title=title or CAPTIONS.get(diagram_type, diagram_type),
                image=payload,
                mime=mime,
                alternates=tuple(
                    (other, value[1]) for other, value in renditions.items() if other != mime
                ),
            )
        )
    return figures


async def run_export(export_id: str, session_factory=SessionFactory) -> ExportOutcome:
    started = datetime.now(UTC)

    async with session_factory() as session:
        request = await session.get(ExportRow, export_id)
        if request is None:
            raise ExportNotFound(f"no export {export_id!r}")
        if request.status == "succeeded":
            # Idempotent, like every other job: a retry must not re-render a
            # document the user may already have downloaded.
            return ExportOutcome(
                export_id=export_id,
                status=request.status,
                format=request.format,
                size=len(request.content or b""),
                duration_ms=request.duration_ms or 0,
            )

        run = await session.get(GenerationRunRow, request.run_id)
        if run is None:
            raise ExportNotFound(f"export {export_id!r} references a run that is gone")
        version = await session.get(CPMVersionRow, run.cpm_version_id)
        figures = await gather_figures(session, run)

        request.status = "running"
        await session.commit()

    status = "succeeded"
    error: str | None = None
    content = b""
    counts = (0, 0)

    try:
        cpm = CPM.model_validate(version.payload)
        assembled = await assemble_srs(cpm, figures, cpm_version_id=version.id, run_id=run.id)
        template = get_template(request.template_id)
        inputs = TemplateInputs(values=dict(request.fields))
        document = apply_template(assembled.document, template, inputs)
        resolved = to_document_template(template, inputs)

        if request.format == "pdf":
            result = export_pdf(document, resolved)
        else:
            result = export_docx(document, resolved)
        content = result.content
        counts = (result.figures, result.tables)
    except MissingTemplateFields as exc:
        status, error = "failed", str(exc)
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("export %s failed", export_id)

    completed = datetime.now(UTC)
    duration_ms = int((completed - started).total_seconds() * 1000)

    async with session_factory() as session:
        request = await session.get(ExportRow, export_id)
        request.status = status
        request.error = error
        request.content = content or None
        request.figures, request.tables = counts
        request.duration_ms = duration_ms
        request.completed_at = completed
        await session.commit()

    return ExportOutcome(
        export_id=export_id,
        status=status,
        format=request.format,
        size=len(content),
        duration_ms=duration_ms,
        error=error,
    )
