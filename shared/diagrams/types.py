"""Types shared by mappers, engines and the renderer."""

from dataclasses import dataclass
from enum import StrEnum


class Engine(StrEnum):
    """Rendering backends.

    Fixed by SRS §8 and not extended by adding a diagram type: Mermaid cannot
    render use case, component or deployment diagrams, so PlantUML is a hard
    dependency rather than a preference.
    """

    PLANTUML = "plantuml"
    MERMAID = "mermaid"


class RenderFormat(StrEnum):
    SVG = "svg"
    PNG = "png"


@dataclass(frozen=True)
class RenderedDiagram:
    diagram_type: str
    title: str
    engine: str
    source: str
    fmt: RenderFormat
    content: bytes

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class FailedDiagram:
    """One diagram that could not be produced.

    Carries the source that failed, so the failure is diagnosable without
    re-running the generation. Returning this rather than raising is what keeps
    a single bad diagram from taking the whole run down (FR-11, NFR-R2).
    """

    diagram_type: str
    title: str
    engine: str
    source: str
    error: str
    attempts: int

    @property
    def ok(self) -> bool:
        return False


@dataclass(frozen=True)
class SkippedDiagram:
    """Not produced, because the model does not describe it.

    Deliberately distinct from `FailedDiagram`. "We could not draw this" and
    "you never told us about this" need different words in the document and
    different actions from the user, and collapsing them would let a genuine
    render failure hide behind a shrug.
    """

    diagram_type: str
    title: str
    reason: str

    @property
    def ok(self) -> bool:
        return False


DiagramResult = RenderedDiagram | FailedDiagram | SkippedDiagram
