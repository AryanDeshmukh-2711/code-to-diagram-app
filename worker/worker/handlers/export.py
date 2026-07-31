"""Producing a document, in the worker (C-4).

Export was the last generation path still running inside an HTTP request. At
fifteen pages that was a second and nobody noticed; at forty it approaches the
NFR-P4 budget, and a request holding a connection open for half a minute is a
request that dies behind a proxy timeout with nothing to show for it.

It is the same shape as every other generation stage now: the API records the
job and returns, the worker does the work, and the result is fetched through a
signed link.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def export_document(ctx: dict[str, Any], export_id: str) -> dict[str, Any]:
    """Assemble and render one export request."""
    from generation.export import ExportNotFound, run_export

    try:
        outcome = await run_export(export_id)
    except ExportNotFound:
        # Nothing to retry: the request or its run is gone.
        logger.error("export %s no longer exists", export_id)
        return {"exportId": export_id, "status": "missing"}

    logger.info(
        "export %s %s in %dms (%s, %d bytes)",
        export_id,
        outcome.status,
        outcome.duration_ms,
        outcome.format,
        outcome.size,
    )
    return {
        "exportId": export_id,
        "status": outcome.status,
        "durationMs": outcome.duration_ms,
        "bytes": outcome.size,
        "error": outcome.error,
    }
