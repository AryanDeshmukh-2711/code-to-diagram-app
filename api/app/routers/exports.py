"""Exporting a finished run, and the last step of the funnel.

Two things converge here. It is where the tier's export entitlement is
actually enforced (FR-22) — the check existed before this endpoint did, which
meant DOCX was restricted in principle and available to anyone in practice.
And it is the event that closes the funnel: a run that was generated but never
exported is a drop-off, and until something recorded the export there was no
way to see that drop.
"""

from typing import Any

from analytics import events
from billing.quota import QuotaExceeded, check_export
from cpm.schema import CPM
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from srs.assemble import assemble_srs
from srs.export.docx import export_docx
from srs.export.pdf import export_pdf
from srs.export.template import FREE_TIER
from srs.ieee830 import CAPTIONS, FigureInput
from srs.template.apply import (
    MissingTemplateFields,
    TemplateInputs,
    apply_template,
    get_template,
    to_document_template,
)
from store.models import CPMVersionRow, GenerationArtefactRow, GenerationRunRow
from store.session import SessionFactory

from app.core.quota import as_http

router = APIRouter(prefix="/runs", tags=["exports"])

MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MIME_OF_FORMAT = {"svg": "image/svg+xml", "png": "image/png"}


class ExportIn(BaseModel):
    format: str = "pdf"
    templateId: str = "ieee-830-plain"
    accountId: str = "anonymous"
    fields: dict[str, str] = Field(default_factory=dict)


@router.post("/{run_id}/export")
async def export_run(run_id: str, body: ExportIn) -> Response:
    if body.format not in MEDIA:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported export format {body.format!r}; use pdf or docx",
        )

    async with SessionFactory() as session:
        try:
            tier = await check_export(session, body.accountId, body.format)
        except QuotaExceeded as exc:
            raise as_http(exc) from None

        run = await session.get(GenerationRunRow, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no run {run_id!r}")
        if run.status != "succeeded":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"run {run_id!r} is {run.status}; only a succeeded run can be exported",
            )

        version = await session.get(CPMVersionRow, run.cpm_version_id)
        # Every rendition of this model, not just this run's. DOCX cannot embed
        # SVG and PDF prefers it, so a project that has been rendered both ways
        # should export either format without being told to re-render. The
        # run's own format is the primary; the rest become alternates.
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

    primary_mime = MIME_OF_FORMAT.get(run.fmt, "image/png")
    figures = []
    for diagram_type, renditions in sorted(by_type.items()):
        mime = primary_mime if primary_mime in renditions else next(iter(renditions))
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

    if body.format == "docx" and not any(
        figure.rendition_available("image/png") for figure in figures
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "needs_png",
                "message": (
                    "DOCX embeds raster images, and this model has only been "
                    "rendered as SVG. Generate once with format=png and the "
                    "export will use it."
                ),
            },
        )

    cpm = CPM.model_validate(version.payload)
    assembled = await assemble_srs(cpm, figures, cpm_version_id=version.id, run_id=run_id)

    template = get_template(body.templateId)
    inputs = TemplateInputs(values=dict(body.fields))
    try:
        document = apply_template(assembled.document, template, inputs)
    except MissingTemplateFields as exc:
        # A missing institution name is the user's to supply, not an error to
        # apologise for: 422 with every missing field named at once.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "template_fields", "missing": exc.missing, "message": str(exc)},
        ) from None

    resolved = to_document_template(template, inputs)
    if body.format == "pdf":
        # FR-20: the watermark is a property of the plan, applied at render.
        result = export_pdf(document, resolved, FREE_TIER if tier.watermark else None)
    else:
        result = export_docx(document, resolved)

    async with SessionFactory() as session:
        await events.record(
            session,
            events.EXPORT_COMPLETED,
            account_id=body.accountId,
            project_id=run.project_id,
            run_id=run_id,
            tier=tier.id,
            payload={
                "format": body.format,
                "templateId": body.templateId,
                "bytes": result.size,
                "figures": result.figures,
                "tables": result.tables,
                "watermarked": bool(tier.watermark and body.format == "pdf"),
            },
        )
        await session.commit()

    filename = f"{cpm.meta.project_name.replace(' ', '_')}_SRS.{body.format}"
    return Response(
        content=result.content,
        media_type=MEDIA[body.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class MetricsQuery(BaseModel):
    days: int = 30


metrics_router = APIRouter(tags=["metrics"])


@metrics_router.get("/metrics", response_class=Response)
async def dashboard(days: int = 30) -> Response:
    """The dashboard. Server-rendered, no analytics SDK, no outbound request."""
    from analytics.dashboard import render
    from analytics.metrics import collect

    page = render(await collect(days))
    return Response(content=page, media_type="text/html; charset=utf-8")


@metrics_router.get("/metrics.json")
async def metrics_json(days: int = 30) -> dict[str, Any]:
    from dataclasses import asdict

    from analytics.metrics import collect

    return asdict(await collect(days))
