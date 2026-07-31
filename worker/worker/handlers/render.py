"""Stage 2: confirmed CPM -> diagram source -> rendered SVG/PNG.

Runs here and nowhere else (C-4). The HTTP handler creates the run row and
enqueues; a request never waits on a render.

Deterministic (FR-9): identical CPM plus identical options must yield identical
diagram source, and no LLM call belongs in this path.
"""

import logging
from typing import Any

from diagrams.renderer import build_default_renderer
from generation.orchestrator import RunNotFound, execute_run

logger = logging.getLogger(__name__)


async def render_run(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Execute one persisted generation run.

    Safe to call more than once for the same run_id: a run that already
    succeeded returns immediately, and an interrupted one upserts its artefacts
    rather than duplicating them (NFR-R3).
    """
    try:
        outcome = await execute_run(run_id, build_default_renderer())
    except RunNotFound:
        # Nothing to retry — the run or its CPM version is gone. Raising would
        # have arq retry a job that can never succeed.
        logger.error("generation run %s no longer exists", run_id)
        return {"runId": run_id, "status": "missing"}

    logger.info(
        "run %s %s in %dms (%d ok, %d failed, %d skipped)",
        outcome.run_id,
        outcome.status,
        outcome.duration_ms,
        outcome.succeeded,
        outcome.failed,
        outcome.skipped,
    )
    return {
        "runId": outcome.run_id,
        "status": outcome.status,
        "durationMs": outcome.duration_ms,
        "succeeded": outcome.succeeded,
        "failed": outcome.failed,
        "skipped": outcome.skipped,
        "llmCostUsd": outcome.llm_cost_usd,
    }
