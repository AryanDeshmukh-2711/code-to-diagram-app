"""Stage 1: normalised input -> CPM. The worker's half of C-4.

The ONLY stage permitted to call the LLM, and only via the LLM Gateway.
Everything downstream renders from the CPM this produces. The API's half
writes an `ExtractionRow` and enqueues; this is where the model actually runs.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def extract_cpm(ctx: dict[str, Any], extraction_id: str) -> dict[str, Any]:
    """Run one extraction request."""
    from generation.extraction import ExtractionNotFound, run_extraction

    try:
        outcome = await run_extraction(extraction_id)
    except ExtractionNotFound:
        # Nothing to retry: the request is gone.
        logger.error("extraction %s no longer exists", extraction_id)
        return {"extractionId": extraction_id, "status": "missing"}

    logger.info(
        "extraction %s %s (%s) in %dms",
        outcome.extraction_id,
        outcome.status,
        outcome.outcome or "n/a",
        outcome.duration_ms,
    )
    return {
        "extractionId": outcome.extraction_id,
        "status": outcome.status,
        "outcome": outcome.outcome,
        "durationMs": outcome.duration_ms,
        "error": outcome.error,
    }
