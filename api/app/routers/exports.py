"""Requesting a document, collecting it, and the last step of the funnel.

Three things converge here. It is where the tier's export entitlement is
enforced (FR-22). It is where the funnel closes: a run that was generated and
never exported is a drop-off, and until something recorded the export there was
no way to see that drop. And, since the pre-launch review, it is the last
generation path that stopped running inside an HTTP request.

C-4 now holds everywhere. This endpoint checks, writes a row and enqueues; the
worker assembles and renders; the finished file is collected through a signed,
expiring link. A forty-page document no longer holds a connection open for the
length of its own rendering.
"""

import uuid
from typing import Any

from analytics import events
from arq import create_pool
from arq.connections import RedisSettings
from billing.quota import QuotaExceeded, account_tier, check_export
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from generation.export import gather_figures
from pydantic import BaseModel, Field
from sqlalchemy import select
from srs.template.apply import (
    MissingTemplateFields,
    TemplateInputs,
    available_templates,
    check_fields,
)
from store.models import ExportRow, GenerationArtefactRow
from store.session import SessionFactory

from app.core.config import get_settings
from app.core.identity import owned_run, require_account, sign, verify
from app.core.quota import as_http

router = APIRouter(prefix="/runs", tags=["exports"])

MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ExportIn(BaseModel):
    format: str = "pdf"
    templateId: str = "ieee-830-plain"
    fields: dict[str, str] = Field(default_factory=dict)


class ExportOut(BaseModel):
    exportId: str
    status: str
    format: str
    url: str | None = None
    bytes: int | None = None
    error: str | None = None
    watermarked: bool = False
    tier: str | None = None


@router.post("/{run_id}/export", status_code=status.HTTP_202_ACCEPTED)
async def export_run(
    run_id: str, body: ExportIn, account: str = Depends(require_account)
) -> ExportOut:
    """Queue an export. Returns 202; nothing is rendered here (C-4)."""
    if body.format not in MEDIA:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported export format {body.format!r}; use pdf or docx",
        )

    async with SessionFactory() as session:
        try:
            tier = await check_export(session, account, body.format)
        except QuotaExceeded as exc:
            raise as_http(exc) from None

        run = await owned_run(session, run_id, account)
        if run.status != "succeeded":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"run {run_id!r} is {run.status}; only a succeeded run can be exported",
            )

        # Cheap, and worth doing in the request: a DOCX with no raster to embed
        # would fail in the worker, where the user cannot see why.
        figures = await gather_figures(session, run)
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

        templates = available_templates()
        template = templates.get(body.templateId)
        if template is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"no template {body.templateId!r}; available: "
                f"{', '.join(sorted(templates))}",
            )

        # FR-15, checked here for the same reason needs_png is: cheap, and a
        # missing field is far more useful named now than discovered by the
        # worker with nobody watching. Every missing field at once, never one
        # at a time — check_fields already guarantees that.
        try:
            check_fields(template, TemplateInputs(values=dict(body.fields)))
        except MissingTemplateFields as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "missing_fields",
                    "message": str(exc),
                    "missing": exc.missing,
                },
            ) from None

        request = ExportRow(
            id=f"exp_{uuid.uuid4().hex[:16]}",
            run_id=run_id,
            account_id=account,
            tier=tier.id,
            format=body.format,
            template_id=body.templateId,
            fields=dict(body.fields),
            watermarked=bool(tier.watermark and body.format == "pdf"),
            status="pending",
        )
        session.add(request)
        await session.commit()
        export_id = request.id

    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        await pool.enqueue_job(
            "export_document",
            export_id,
            _job_id=f"export:{export_id}",
            _queue_name=f"arq:{tier.queue}",
        )
    finally:
        await pool.aclose()

    return ExportOut(
        exportId=export_id,
        status="pending",
        format=body.format,
        watermarked=bool(tier.watermark and body.format == "pdf"),
        tier=tier.id,
    )


@router.get("/{run_id}/artefacts")
async def artefact_links(run_id: str, account: str = Depends(require_account)) -> dict[str, Any]:
    """Signed, expiring links to this run's diagrams (NFR-S4)."""
    async with SessionFactory() as session:
        await owned_run(session, run_id, account)
        rows = list(
            await session.scalars(
                select(GenerationArtefactRow).where(GenerationArtefactRow.run_id == run_id)
            )
        )
    return {
        "runId": run_id,
        "artefacts": [
            {
                "diagramType": row.diagram_type,
                "format": row.format,
                "bytes": len(row.content) if row.content else 0,
                "url": f"/artefacts/{row.id}?token={sign(row.id)}",
            }
            for row in rows
            if row.status == "succeeded" and row.content
        ],
    }


class TemplateFieldOut(BaseModel):
    key: str
    label: str
    kind: str
    required: bool
    placeholder: str
    help: str


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str
    fields: list[TemplateFieldOut]


templates_router = APIRouter(tags=["exports"])


@templates_router.get("/templates", response_model=list[TemplateOut])
async def list_templates(account: str = Depends(require_account)) -> list[TemplateOut]:
    """Every template this account's tier may export with, fields and all
    (FR-15). The chat surface reads labels, placeholders and required-ness
    from here — it is not allowed to know what a template needs any other
    way."""
    async with SessionFactory() as session:
        tier = await account_tier(session, account)

    return [
        TemplateOut(
            id=template.id,
            name=template.name,
            description=template.description,
            fields=[
                TemplateFieldOut(
                    key=field.key,
                    label=field.label,
                    kind=field.kind,
                    required=field.required,
                    placeholder=field.placeholder,
                    help=field.help,
                )
                for field in template.fields
            ],
        )
        for template in sorted(available_templates().values(), key=lambda t: t.id)
        if tier.allows_template(template.id)
    ]


artefact_router = APIRouter(tags=["exports"])


@artefact_router.get("/exports/{export_id}", response_model=ExportOut)
async def export_status(export_id: str, account: str = Depends(require_account)) -> ExportOut:
    """Where the export got to, and a signed link once it is finished.

    Unprefixed, like its sibling download route below: an export has its own
    id and is not addressed through the run that produced it, the same
    reason `/exports/{export_id}/download` was never `/runs/exports/...`.
    """
    async with SessionFactory() as session:
        request = await session.get(ExportRow, export_id)
        if request is None or request.account_id != account:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no export {export_id!r}")

        finished = request.status == "succeeded"
        payload = ExportOut(
            exportId=export_id,
            status=request.status,
            format=request.format,
            bytes=len(request.content or b"") or None,
            error=request.error,
            url=(f"/exports/{export_id}/download?token={sign(export_id)}" if finished else None),
            watermarked=request.watermarked,
            tier=request.tier,
        )

        if finished:
            await events.record(
                session,
                events.EXPORT_COMPLETED,
                account_id=account,
                run_id=request.run_id,
                tier=request.tier,
                payload={
                    "format": request.format,
                    "templateId": request.template_id,
                    "bytes": len(request.content or b""),
                    "figures": request.figures,
                    "tables": request.tables,
                    "watermarked": request.watermarked,
                },
            )
            await session.commit()

    return payload


@artefact_router.get("/exports/{export_id}/download")
async def download_export(export_id: str, token: str) -> Response:
    """The finished document, to a signed link (NFR-S4)."""
    verify(export_id, token)

    async with SessionFactory() as session:
        request = await session.get(ExportRow, export_id)
    if request is None or not request.content:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such export")

    return Response(
        content=request.content,
        media_type=MEDIA[request.format],
        headers={"Content-Disposition": f'attachment; filename="SRS.{request.format}"'},
    )


@artefact_router.get("/artefacts/{artefact_id}")
async def download_artefact(artefact_id: str, token: str) -> Response:
    """Serve one diagram to a signed link, and to nothing else.

    Deliberately not behind the account header as well: the signature *is* the
    authorisation, which is what lets a link be embedded or opened in a new
    tab. It is scoped to one artefact and it expires.
    """
    verify(artefact_id, token)

    async with SessionFactory() as session:
        row = await session.get(GenerationArtefactRow, artefact_id)
    if row is None or not row.content:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such artefact")

    media = {"svg": "image/svg+xml", "png": "image/png"}.get(row.format, "application/octet-stream")
    return Response(
        content=row.content, media_type=media, headers={"Cache-Control": "private, max-age=300"}
    )


metrics_router = APIRouter(tags=["metrics"])


@metrics_router.get("/metrics", response_class=Response)
async def dashboard(days: int = 30) -> Response:
    """The dashboard. Server-rendered, no analytics SDK, no outbound request."""
    from analytics.dashboard import render
    from analytics.metrics import collect

    return Response(content=render(await collect(days)), media_type="text/html; charset=utf-8")


@metrics_router.get("/metrics.json")
async def metrics_json(days: int = 30) -> dict[str, Any]:
    from dataclasses import asdict

    from analytics.metrics import collect

    return asdict(await collect(days))
