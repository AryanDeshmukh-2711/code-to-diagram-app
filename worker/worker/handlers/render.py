"""Stage 2: confirmed CPM -> diagram source -> rendered SVG/PNG.

Deterministic (FR-9): identical CPM plus identical options must yield identical
diagram source. No LLM call belongs here.
"""

from typing import Any


async def render_diagram(ctx: dict[str, Any], run_id: str, diagram_type: str) -> None:
    raise NotImplementedError("M1: diagram rendering not implemented")
