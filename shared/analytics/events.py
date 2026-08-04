"""The funnel, as an append-only event log.

One table, one row per thing that happened, a JSONB payload for whatever that
kind of thing carries. No third-party SDK: the numbers that decide whether
this product lives are not going to live in someone else's account, behind
someone else's sampling, subject to someone else's ad blocker. A student's ad
blocker eating the "confirmed with zero edits" event would silently corrupt
the single most important number in the product.

Events are recorded server-side, from the same request that did the thing, so
a step cannot be reported without having happened. The funnel is derived by
querying this table; nothing maintains a counter, because a counter that
drifts from the log is a number nobody can check.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from store.models import EventRow

logger = logging.getLogger(__name__)

# The funnel, in order. PRD section 9.
SIGNUP = "signup"
PROJECT_CREATED = "project_created"
CPM_CONFIRMED = "cpm_confirmed"
RUN_STARTED = "run_started"
RUN_COMPLETED = "run_completed"
EXPORT_COMPLETED = "export_completed"

# Off the main path, but needed for the metrics that judge it.
DIAGRAM_OUTCOME = "diagram_outcome"
REGENERATION_REQUESTED = "regeneration_requested"
QUOTA_REFUSED = "quota_refused"
CHAT_EDIT_APPLIED = "chat_edit_applied"
"""P-M6-2. Recorded once per edit that actually reached the CPM, with the
message that produced it in the payload — the trace from a chat message to
the op it caused, without a second table just to hold that link."""

FUNNEL = (SIGNUP, PROJECT_CREATED, CPM_CONFIRMED, RUN_STARTED, EXPORT_COMPLETED)
"""The five steps a drop-off is measured between. RUN_COMPLETED is deliberately
not a funnel step: a run that succeeded but was never exported is a *drop-off*
between starting and exporting, and folding it in would hide that."""


async def record(
    session,
    name: str,
    *,
    account_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    tier: str | None = None,
    payload: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> EventRow:
    """Append one event. Never raises into the caller's path.

    Instrumentation must not be able to fail a request. A metric that takes
    the product down when the analytics table is locked is worse than no
    metric, and the failure is logged loudly enough to notice.
    """
    row = EventRow(
        id=f"evt_{uuid.uuid4().hex[:20]}",
        name=name,
        account_id=account_id,
        project_id=project_id,
        run_id=run_id,
        tier=tier,
        payload=payload or {},
        occurred_at=occurred_at or datetime.now(UTC),
    )
    try:
        session.add(row)
        await session.flush()
    except Exception:  # pragma: no cover - defensive
        logger.exception("could not record %s event", name)
    return row
