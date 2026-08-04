"""Chat edit-intent parsing. The worker's half of C-4.

The only other stage permitted to call the LLM (the other is `extract_cpm`),
and only via the LLM Gateway. Unlike extraction it never produces an artefact
or rebuilds the CPM outright — its only output is a candidate op, applied
through the same path a form submission on the review screen already uses.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def parse_chat_edit(ctx: dict[str, Any], edit_id: str) -> dict[str, Any]:
    """Run one chat edit-intent request."""
    from generation.chat_edit import ChatEditNotFound, run_chat_edit

    try:
        outcome = await run_chat_edit(edit_id)
    except ChatEditNotFound:
        logger.error("chat edit %s no longer exists", edit_id)
        return {"editId": edit_id, "status": "missing"}

    logger.info(
        "chat edit %s %s (%s) in %dms",
        outcome.edit_id,
        outcome.status,
        outcome.outcome or "n/a",
        outcome.duration_ms,
    )
    return {
        "editId": outcome.edit_id,
        "status": outcome.status,
        "outcome": outcome.outcome,
        "durationMs": outcome.duration_ms,
        "error": outcome.error,
    }
