"""Diagram rendering: CPM -> mapper -> source -> engine -> SVG/PNG.

The mapper stage is a pure function of the CPM with no LLM anywhere in it
(FR-9). That is not a style preference: a model call here would mean two
renders of the same CPM could disagree with each other and with the SRS prose,
which is FR-9 and FR-10 broken together. `test_diagram_purity.py` enforces it.

Adding a diagram type is one new file under `diagrams/mappers/`. The registry
discovers it, the mapper declares its own engine, and nothing else changes.
"""

from diagrams.engines import (
    DiagramEngine,
    EngineError,
    EngineUnavailable,
    MermaidEngine,
    PlantUMLEngine,
)
from diagrams.mapper import DiagramMapper, InsufficientModelData
from diagrams.registry import (
    MapperRegistrationError,
    UnknownDiagramType,
    get_mapper,
    registered_types,
    registry,
)
from diagrams.renderer import MAX_ATTEMPTS, DiagramRenderer
from diagrams.types import (
    DiagramResult,
    Engine,
    FailedDiagram,
    RenderedDiagram,
    RenderFormat,
    SkippedDiagram,
)

__all__ = [
    "MAX_ATTEMPTS",
    "DiagramEngine",
    "DiagramMapper",
    "DiagramRenderer",
    "DiagramResult",
    "Engine",
    "EngineError",
    "EngineUnavailable",
    "FailedDiagram",
    "InsufficientModelData",
    "MapperRegistrationError",
    "MermaidEngine",
    "PlantUMLEngine",
    "RenderFormat",
    "RenderedDiagram",
    "SkippedDiagram",
    "UnknownDiagramType",
    "get_mapper",
    "registered_types",
    "registry",
]
