"""Stage 1: normalised input -> CPM.

The ONLY stage permitted to call the LLM, and only via the LLM Gateway.
Everything downstream renders from the CPM this produces.
"""

from typing import Any


async def extract_cpm(ctx: dict[str, Any], project_id: str) -> None:
    raise NotImplementedError("M1: CPM extraction not implemented")
