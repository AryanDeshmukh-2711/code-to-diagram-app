"""What a diagram mapper is.

A mapper is a **pure function of the CPM**. Same CPM in, byte-identical source
out (FR-9). No I/O, no clock, no randomness, and above all no LLM — a single
model call in this path would destroy FR-9 and FR-10 together, because two
renders of the same model could then disagree with each other and with the
document.

Adding a diagram type means adding one module under `mappers/` that exposes a
module-level `MAPPER`. Nothing else in the codebase changes: the registry
discovers it, and the mapper itself declares which engine it needs.
"""

from collections.abc import Callable
from dataclasses import dataclass

from cpm.schema import CPM
from diagrams.types import Engine


@dataclass(frozen=True)
class DiagramMapper:
    diagram_type: str
    """Stable slug, e.g. "class". Deliberately a string rather than a member of
    a central enum — an enum would have to be edited to add a type, and the
    whole point is that adding one touches a single new file."""

    title: str
    """Human-readable caption, used for the numbered figure in the SRS."""

    engine: Engine
    """Declared by the mapper, not chosen by a switch statement elsewhere."""

    to_source: Callable[[CPM], str]
    """The pure function. Must not be a coroutine — see the guardrail test."""
