"""Stage 3: CPM + rendered diagrams + template -> SRS document.

Runs the FR-10 consistency validator before emitting anything: every entity and
actor name must be byte-identical to the CPM, and the run fails if it is not.
"""

from typing import Any


async def assemble_document(ctx: dict[str, Any], run_id: str) -> None:
    raise NotImplementedError("M1: document assembly not implemented")
