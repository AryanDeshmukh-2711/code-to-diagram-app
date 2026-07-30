"""CPM -> PlantUML use case diagram.

PlantUML is not a preference here: Mermaid has no use case diagram at all
(CLAUDE.md, SRS §8). Pure function.
"""

from cpm.schema import CPM
from diagrams.mapper import DiagramMapper
from diagrams.text import alias, quote
from diagrams.types import Engine

_HEADER = [
    "@startuml",
    "!theme plain",
    "left to right direction",
    "skinparam packageStyle rectangle",
    "skinparam shadowing false",
    "",
]


def to_source(cpm: CPM) -> str:
    lines = list(_HEADER)

    for actor in cpm.actors:
        lines.append(f"actor {quote(actor.name)} as {alias(actor.id)}")
    if cpm.actors:
        lines.append("")

    lines.append(f"rectangle {quote(cpm.meta.project_name)} {{")
    for use_case in cpm.use_cases:
        lines.append(f"  usecase {quote(use_case.name)} as {alias(use_case.id)}")
    lines.append("}")
    lines.append("")

    for use_case in cpm.use_cases:
        for actor_id in use_case.actors:
            lines.append(f"{alias(actor_id)} --> {alias(use_case.id)}")

    if any(use_case.actors for use_case in cpm.use_cases):
        lines.append("")

    lines.append("@enduml")
    return "\n".join(lines) + "\n"


MAPPER = DiagramMapper(
    diagram_type="use_case",
    title="Use Case Diagram",
    engine=Engine.PLANTUML,
    to_source=to_source,
)
