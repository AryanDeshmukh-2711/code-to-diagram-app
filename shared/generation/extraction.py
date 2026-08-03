"""Executing an extraction request. The worker's half of C-4.

The API's half writes an `ExtractionRow` and enqueues; this is what actually
calls the model. `ExtractionService` does the real work — building the CPM,
enforcing the FR-5 floor, normalising near-duplicates — and this module's job
is only to feed it the right text, in the right shape, and record what came
back. It does not reimplement any of that.

Where the text comes from is the one thing this module decides. For a PDF
upload, `extract_pdf_text` runs here and only here — the per-page work that
must never happen in the request cycle. For pasted text, there is nothing to
do but pass it straight through. Either way, by the time text reaches
`ExtractionService.extract`, it is handled exactly like any other extraction
input: DATA to the gateway, delimited and neutralised the same way
`cpm_extraction` has always done it. No new path is created here.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from extraction.pdf_text import extract_pdf_text
from extraction.result import Extracted, InsufficientInput
from extraction.service import ExtractionService
from llm.gateway import build_default_gateway
from store.models import CPMDraftRow, ExtractionRow
from store.session import SessionFactory

logger = logging.getLogger(__name__)


class ExtractionNotFound(LookupError):
    pass


@dataclass(frozen=True)
class ExtractionOutcome:
    extraction_id: str
    status: str
    outcome: str | None
    duration_ms: int
    error: str | None = None


async def run_extraction(extraction_id: str, session_factory=SessionFactory) -> ExtractionOutcome:
    started = datetime.now(UTC)

    async with session_factory() as session:
        row = await session.get(ExtractionRow, extraction_id)
        if row is None:
            raise ExtractionNotFound(f"no extraction {extraction_id!r}")
        if row.status == "succeeded":
            # Idempotent, like every other job: a retry must not re-run the
            # model against text that already produced a draft (or an honest
            # insufficient-input result the user has already seen).
            return ExtractionOutcome(
                extraction_id=extraction_id,
                status=row.status,
                outcome=row.outcome,
                duration_ms=row.duration_ms or 0,
            )

        project_id = row.project_id
        project_name = None  # resolved below, from CPMDraftRow if one exists
        text = row.source_text
        pdf_bytes = row.source_pdf

        row.status = "running"
        await session.commit()

        existing_draft = await session.get(CPMDraftRow, project_id)
        if existing_draft is not None:
            project_name = existing_draft.project_name

    status = "succeeded"
    outcome: str | None = None
    error: str | None = None

    try:
        if pdf_bytes is not None:
            # The only place this runs: full per-page extraction, off the
            # request cycle, bounded by the worker's own job timeout rather
            # than by an HTTP client's patience.
            text = extract_pdf_text(pdf_bytes)
        if not text or not text.strip():
            raise ValueError("no text could be extracted from the upload")

        service = ExtractionService(build_default_gateway())
        result = await service.extract(
            text,
            project_name=project_name or project_id,
            user_id=row.account_id,
        )
    except Exception as exc:
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("extraction %s failed", extraction_id)
        result = None

    word_count = entities_found = relationships_found = None
    reason = None
    guidance: list[str] = []
    notes: list[str] = []
    draft_ready = False

    if isinstance(result, Extracted):
        outcome = "extracted"
        notes = list(result.notes)
        async with session_factory() as session:
            draft = await session.get(CPMDraftRow, project_id)
            payload = result.cpm.model_dump(by_alias=True, mode="json")
            if draft is None:
                session.add(
                    CPMDraftRow(
                        project_id=project_id,
                        project_name=result.cpm.meta.project_name,
                        payload=payload,
                    )
                )
            else:
                draft.project_name = result.cpm.meta.project_name
                draft.payload = payload
            await session.commit()
        draft_ready = True
    elif isinstance(result, InsufficientInput):
        outcome = "insufficient"
        reason = result.reason
        guidance = list(result.guidance)
        word_count = result.word_count
        entities_found = result.entities_found
        relationships_found = result.relationships_found

    completed = datetime.now(UTC)
    duration_ms = int((completed - started).total_seconds() * 1000)

    async with session_factory() as session:
        row = await session.get(ExtractionRow, extraction_id)
        row.status = status
        row.outcome = outcome
        row.error = error
        row.word_count = word_count
        row.entities_found = entities_found
        row.relationships_found = relationships_found
        row.reason = reason
        row.guidance = guidance
        row.notes = notes
        row.cpm_draft_ready = draft_ready
        row.duration_ms = duration_ms
        row.completed_at = completed
        # The raw PDF has done its job; there is no reason to keep an
        # uploaded document around once its text has been pulled out of it.
        row.source_pdf = None
        await session.commit()

    return ExtractionOutcome(
        extraction_id=extraction_id,
        status=status,
        outcome=outcome,
        duration_ms=duration_ms,
        error=error,
    )
