"""AT-1 — the acceptance test that decides whether V1 works.

SRS §10.1. One 300-word description goes in at the top; a submission-ready
PDF and DOCX come out at the bottom; every claim the product makes about
what happens in between is checked on the way.

Run it with:

    make at1

Two things about how it is written.

Every assertion is evaluated independently and reported by name. A failure
prints what was expected, what was found, and — where the cause is known —
what to do about it. It does not print a traceback, because a traceback tells
you where Python gave up, not which promise the product broke. One broken
promise also does not stop the others being checked: the pipeline runs as far
as it can and the report says how far that was.

The extraction step needs a model. When none is reachable the recorded model
output is replayed through the *real* gateway and the *real* extraction
service, so the schema validation, de-duplication, orphan dropping and floor
check all still run — only the neural step is replayed. The report says so in
bold terms, and the run is not counted as a full AT-1 pass.
"""

import argparse
import asyncio
import io
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from report import GREY, RED, RESET, Report

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DESCRIPTION = FIXTURES / "description.txt"
RECORDING = FIXTURES / "recorded_model_output.json"

PROJECT_NAME = "Library Management System"
AUTHOR = "A. V. Deshmukh"

V1_DIAGRAMS = (
    "class",
    "use_case",
    "sequence",
    "activity",
    "state",
    "component",
    "deployment",
    "entity_relationship",
)
"""The eight types V1 promises (CLAUDE.md, SRS §8). Written out here rather
than read from the registry on purpose: a test that asks the code what it
supports and then checks it supports that can never fail."""

BUDGET_SECONDS = 180.0
MIN_PDF_PAGES = 12
MIN_ENTITIES = 5
MIN_RELATIONSHIPS = 4

BASE = os.getenv("AT1_API", "http://localhost:8000")


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


async def _extract(report: Report, text: str):
    """Description -> CPM, through the real gateway and extraction service."""
    from extraction.service import ExtractionService
    from llm.config import TASKS
    from llm.gateway import LLMGateway

    provider_name = os.getenv("LLM_PROVIDER", "ollama")
    recorded = json.loads(RECORDING.read_text(encoding="utf-8"))

    reachable = await _model_reachable()
    if reachable:
        from llm.providers.ollama import OllamaProvider

        providers = {provider_name: OllamaProvider(os.getenv("LLM_BASE_URL", ""))}
        tasks = TASKS
        report.notes.append(
            f"extraction  performed by {TASKS['cpm_extraction'].model} via {provider_name}"
        )
    else:
        from llm.providers.scripted import ScriptedProvider

        providers = {"scripted": ScriptedProvider([json.dumps(recorded)])}
        tasks = {
            name: type(config)(**{**config.__dict__, "provider": "scripted"})
            for name, config in TASKS.items()
        }
        report.replayed = True
        report.notes.append(
            f"extraction  {RED}REPLAYED{RESET} from {RECORDING.name} — no model server "
            f"reachable"
        )
        report.notes.append(
            f"            {GREY}the gateway, schema validation, de-duplication, orphan "
            f"dropping{RESET}"
        )
        report.notes.append(
            f"            {GREY}and the FR-5 floor all still run; only the model call is "
            f"replayed{RESET}"
        )

    service = ExtractionService(LLMGateway(providers=providers, tasks=tasks))
    return await service.extract(
        text,
        project_name=PROJECT_NAME,
        authors=[AUTHOR],
        created_at=datetime.now(UTC),
    )


async def _model_reachable() -> bool:
    base = os.getenv("LLM_BASE_URL")
    if not base:
        return False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.get(f"{base.rstrip('/')}/api/tags")
        return True
    except Exception:
        return False


async def _entitled_session(client: httpx.AsyncClient) -> tuple[str, dict[str, str]]:
    """Register, sign in, and return the account id with its auth header.

    Through the real endpoints: AT-1 exercises the product a user would meet,
    and an account inserted straight into the database would skip the one thing
    standing between a stranger and somebody's coursework.
    """
    registered = await client.post(f"{BASE}/auth/register", json={})
    registered.raise_for_status()
    account = registered.json()

    session = await client.post(
        f"{BASE}/auth/token",
        json={"accountId": account["accountId"], "apiKey": account["apiKey"]},
    )
    session.raise_for_status()
    return account["accountId"], {"Authorization": f"Bearer {session.json()['token']}"}


async def _confirm_over_http(
    client: httpx.AsyncClient, project_id: str, cpm, auth: dict[str, str]
) -> str:
    """Through the review gate (FR-6), over HTTP, exactly as a user would."""
    payload = cpm.model_dump(by_alias=True, mode="json")
    seeded = await client.post(
        f"{BASE}/projects/{project_id}/review/seed",
        json={"projectName": PROJECT_NAME, "draft": payload},
        headers=auth,
    )
    seeded.raise_for_status()
    confirmed = await client.post(
        f"{BASE}/projects/{project_id}/review/confirm",
        json={},
        headers=auth,
    )
    confirmed.raise_for_status()
    return confirmed.json()["versionId"]


async def _run(
    client: httpx.AsyncClient, project_id: str, version_id: str, types, fmt: str, auth: dict
):
    created = await client.post(
        f"{BASE}/runs",
        json={
            "projectId": project_id,
            "cpmVersionId": version_id,
            "diagramTypes": list(types),
            "format": fmt,
        },
        headers=auth,
    )
    created.raise_for_status()
    run_id = created.json()["runId"]
    deadline = time.perf_counter() + BUDGET_SECONDS
    while time.perf_counter() < deadline:
        run = (
            await client.get(f"{BASE}/runs/{run_id}", headers=auth)
        ).json()
        if run["status"] in ("succeeded", "failed"):
            return run
        await asyncio.sleep(0.2)
    raise TimeoutError(f"run {run_id} did not finish inside the budget")


# ---------------------------------------------------------------------------
# The assertions
# ---------------------------------------------------------------------------


async def run_at1() -> Report:
    from consistency.validator import validate_consistency
    from diagrams.registry import registered_types
    from extraction.service import Extracted
    from sqlalchemy import select
    from srs.assemble import assemble_srs
    from srs.ast import figures as ast_figures
    from srs.ast import walk_sections
    from srs.export.docx import export_docx
    from srs.export.pdf import export_pdf
    from srs.export.template import A4
    from srs.ieee830 import CAPTIONS, FigureInput
    from store.models import GenerationArtefactRow
    from store.session import SessionFactory

    report = Report(
        label="AT-1",
        subtitle=f"{PROJECT_NAME} — end-to-end acceptance (SRS 10.1)",
        budget_seconds=BUDGET_SECONDS,
        success_line="V1 works.",
    )
    started = time.perf_counter()

    text = DESCRIPTION.read_text(encoding="utf-8")
    words = len(text.split())
    report.notes.append(
        f"input       {words}-word description · project {PROJECT_NAME!r} · author {AUTHOR!r}"
    )
    report.notes.append(
        "pipeline    review gate over HTTP · runs through the Redis worker · exports in process"
    )

    # -- 1/2 the model ----------------------------------------------------
    outcome = await _extract(report, text)
    if not isinstance(outcome, Extracted):
        report.add(
            "CPM extracted from the description",
            False,
            f"the extractor reported insufficient input ({outcome.reason})",
            "a CPM",
            "the description is below the FR-5 floor, or the model returned too little",
        )
        report.seconds = time.perf_counter() - started
        return report

    cpm = outcome.cpm
    report.add(
        "CPM entities",
        len(cpm.entities) >= MIN_ENTITIES,
        f"{len(cpm.entities)}",
        f">= {MIN_ENTITIES}",
        "the description does not support five entities, or extraction dropped some",
    )
    report.add(
        "CPM relationships",
        len(cpm.relationships) >= MIN_RELATIONSHIPS,
        f"{len(cpm.relationships)}",
        f">= {MIN_RELATIONSHIPS}",
        "relationships whose endpoints do not resolve are dropped rather than invented",
    )

    # -- 3 eight diagrams --------------------------------------------------
    available = [t for t in V1_DIAGRAMS if t in set(registered_types())]
    missing = [t for t in V1_DIAGRAMS if t not in set(registered_types())]

    project_id = f"at1_{int(time.time())}"
    async with httpx.AsyncClient(timeout=BUDGET_SECONDS) as client:
        account, auth = await _entitled_session(client)
        report.notes.append(f"account     {account}, signed in")
        version_id = await _confirm_over_http(client, project_id, cpm, auth)
        svg_run = await _run(client, project_id, version_id, available, "svg", auth)
        png_run = await _run(client, project_id, version_id, available, "png", auth)

    async with SessionFactory() as session:
        artefacts: dict[str, dict[str, tuple[str, bytes, str]]] = {}
        for run_id, mime in ((svg_run["runId"], "image/svg+xml"), (png_run["runId"], "image/png")):
            for row in await session.scalars(
                select(GenerationArtefactRow).where(GenerationArtefactRow.run_id == run_id)
            ):
                if row.status == "succeeded" and row.content:
                    artefacts.setdefault(row.diagram_type, {})[mime] = (
                        row.title,
                        row.content,
                        row.source or "",
                    )

    rendered = sorted(artefacts)
    report.add(
        "Eight diagrams render",
        len(rendered) == len(V1_DIAGRAMS),
        f"{len(rendered)} of {len(V1_DIAGRAMS)} rendered",
        f"all of {', '.join(V1_DIAGRAMS)}",
        (
            f"no mapper is registered for: {', '.join(missing)}\n"
            f"the registry contains: {', '.join(sorted(registered_types()))}\n"
            f"P-M2-1 has {len(missing)} mappers outstanding; nothing else blocks this"
            if missing
            else "the run failed for a rendered type; see the run's artefact errors"
        ),
    )

    failed = [a for a in svg_run["artefacts"] if a["status"] == "failed"]
    report.add(
        "Every rendered diagram is syntactically valid",
        not failed and svg_run["status"] == "succeeded",
        f"{len(rendered)} valid, {len(failed)} rejected by the engine",
        "zero engine rejections (FR-11)",
        "\n".join(f"{a['diagramType']}: {a['error']}" for a in failed),
    )

    # -- 4 FR-10 ------------------------------------------------------------
    sources = [
        type("Src", (), {"diagram_type": kind, "engine": _engine_of(kind), "source": value[2]})()
        for kind, by_mime in sorted(artefacts.items())
        for value in [by_mime["image/svg+xml"]]
    ]
    consistency = validate_consistency(cpm, sources)
    report.add(
        "Entity naming byte-identical across every diagram",
        consistency.ok and consistency.checked_diagrams == len(rendered),
        (
            f"{consistency.recognised_names} names checked across "
            f"{consistency.checked_diagrams} diagrams, {len(consistency.violations)} mismatches"
        ),
        "zero mismatches, every diagram checked (FR-10)",
        consistency.render() if not consistency.ok else "",
    )

    # -- 5/6/7 the document -------------------------------------------------
    figures = [
        FigureInput(
            diagram_type=kind,
            title=by_mime["image/svg+xml"][0] or CAPTIONS.get(kind, kind),
            image=by_mime["image/svg+xml"][1],
            mime="image/svg+xml",
            alternates=(("image/png", by_mime["image/png"][1]),),
        )
        for kind, by_mime in sorted(artefacts.items())
        if "image/png" in by_mime
    ]
    assembled = await assemble_srs(cpm, figures, cpm_version_id=version_id)
    document = assembled.document
    docx = export_docx(document, A4)
    pdf = export_pdf(document, A4)

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf.content))
    pages = len(reader.pages)
    report.add(
        "PDF page count",
        pages >= MIN_PDF_PAGES,
        f"{pages} pages",
        f">= {MIN_PDF_PAGES}",
        "the document is shorter than a submission; are diagrams or sections missing?",
    )

    embedded = ast_figures(document)
    numbered = [f for f in embedded if f.number]
    captioned = [f for f in embedded if f.caption.strip()]
    report.add(
        "All eight diagrams present as numbered, captioned figures",
        len(embedded) == len(V1_DIAGRAMS)
        and len(numbered) == len(embedded)
        and len(captioned) == len(embedded),
        f"{len(embedded)} figures, {len(numbered)} numbered, {len(captioned)} captioned",
        f"{len(V1_DIAGRAMS)} figures, all numbered and captioned (FR-16)",
        (
            f"only {len(embedded)} diagrams reached the document; "
            f"missing: {', '.join(missing) or 'none'}"
        ),
    )

    pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    cover = " ".join((reader.pages[0].extract_text() or "").split())
    report.add(
        "Cover page carries the project name and author",
        PROJECT_NAME in cover and AUTHOR in cover,
        f"project {'yes' if PROJECT_NAME in cover else 'NO'}, "
        f"author {'yes' if AUTHOR in cover else 'NO'}",
        "both on page 1",
        f"page 1 reads: {cover[:120]}",
    )

    # -- index consistency ---------------------------------------------------
    contents, list_of_figures = document.front_matter[0], document.front_matter[1]
    section_numbers = [s.number for s in walk_sections(document)]
    figure_numbers = [str(f.number) for f in embedded]
    index_matches = (
        [entry.number for entry in contents.entries] == section_numbers
        and [entry.number for entry in list_of_figures.entries] == figure_numbers
    )
    in_pdf = all(
        entry.title in pdf_text for entry in list(contents.entries)[:8]
    )
    report.add(
        "Index entries match the real section and figure numbering",
        index_matches and in_pdf,
        (
            f"{len(contents.entries)} contents entries vs {len(section_numbers)} sections, "
            f"{len(list_of_figures.entries)} figure entries vs {len(embedded)} figures"
        ),
        "index numbering identical to the document's own",
        "the contents table is derived from the numbered tree; a mismatch means "
        "numbering ran twice",
    )

    # -- DOCX vs PDF ---------------------------------------------------------
    from srs.export.compare import (
        compare,
        docx_body_words,
        figure_vocabulary,
        pdf_body_words,
    )

    difference = compare(
        docx_body_words(docx.content),
        pdf_body_words(pdf.content, PROJECT_NAME),
        # A vector figure keeps its own text, so the PDF legitimately contains
        # every name drawn inside a diagram. Those words are explained, not
        # ignored — anything else extra is still a failure.
        figure_vocabulary([by_mime["image/svg+xml"][1] for by_mime in artefacts.values()]),
    )
    report.add(
        "DOCX text matches PDF text",
        difference.ok,
        difference.render(),
        "every DOCX word present in the PDF in order; extras only markers or figure text",
        "a word the DOCX has and the PDF does not means one exporter dropped content",
    )

    report.seconds = time.perf_counter() - started
    report.add(
        "Total wall time",
        report.seconds < BUDGET_SECONDS,
        f"{report.seconds:.1f}s",
        f"< {BUDGET_SECONDS:.0f}s (NFR-P2)",
        "the run exceeded the budget; check queue wait and engine cold starts",
    )
    return report


def _engine_of(diagram_type: str) -> str:
    from diagrams.registry import registry

    return str(registry()[diagram_type].engine)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run acceptance test AT-1")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args()

    try:
        report = asyncio.run(run_at1())
    except Exception as exc:
        print(f"{RED}AT-1 could not run to completion{RESET}: {type(exc).__name__}: {exc}")
        print(f"{GREY}this is a harness failure, not an assertion failure — the stack "
              f"trace follows{RESET}")
        raise

    if args.json:
        print(
            json.dumps(
                {
                    "passed": report.passed,
                    "replayed": report.replayed,
                    "seconds": round(report.seconds, 2),
                    "checks": [
                        {
                            "number": c.number,
                            "name": c.name,
                            "ok": c.ok,
                            "found": c.found,
                            "expected": c.expected,
                        }
                        for c in report.checks
                    ],
                },
                indent=2,
            )
        )
    else:
        print(report.render())
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
