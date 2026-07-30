"""CPM -> PlantUML class diagram.

Pure function. Reads the CPM and returns source; nothing else.
"""

from cpm.schema import CPM, Entity, Relationship, RelationshipType
from diagrams.mapper import DiagramMapper
from diagrams.text import alias, quote
from diagrams.types import Engine

# UML notation per relationship kind. The arrow points from the CPM's `from`
# to its `to`, which is why inheritance reads child --|> parent.
_ARROWS: dict[RelationshipType, str] = {
    RelationshipType.ASSOCIATION: "-->",
    RelationshipType.AGGREGATION: "o--",
    RelationshipType.COMPOSITION: "*--",
    RelationshipType.INHERITANCE: "--|>",
    RelationshipType.DEPENDENCY: "..>",
    RelationshipType.REALIZATION: "..|>",
}

_HEADER = [
    "@startuml",
    "!theme plain",
    "hide empty members",
    "skinparam classAttributeIconSize 0",
    "skinparam shadowing false",
    "",
]


def _entity_block(entity: Entity) -> list[str]:
    lines = [f"class {quote(entity.name)} as {alias(entity.id)} {{"]

    for attribute in entity.attributes:
        marker = " [key]" if attribute.is_key else ""
        required = "" if attribute.is_key or not attribute.is_required else " [required]"
        lines.append(f"  + {attribute.name} : {attribute.type}{marker}{required}")

    if entity.attributes and entity.methods:
        lines.append("  --")

    for method in entity.methods:
        params = ", ".join(method.params)
        lines.append(f"  + {method.name}({params}) : {method.returns}")

    lines.append("}")
    return lines


def _relationship_line(relationship: Relationship) -> str:
    arrow = _ARROWS[relationship.type]
    target = (
        f"{quote(relationship.cardinality)} {alias(relationship.to)}"
        if relationship.cardinality
        else alias(relationship.to)
    )
    line = f"{alias(relationship.from_)} {arrow} {target}"
    if relationship.label:
        line = f"{line} : {relationship.label}"
    return line


def to_source(cpm: CPM) -> str:
    lines = list(_HEADER)

    for entity in cpm.entities:
        lines.extend(_entity_block(entity))
        lines.append("")

    if cpm.relationships:
        for relationship in cpm.relationships:
            lines.append(_relationship_line(relationship))
        lines.append("")

    lines.append("@enduml")
    return "\n".join(lines) + "\n"


MAPPER = DiagramMapper(
    diagram_type="class",
    title="Class Diagram",
    engine=Engine.PLANTUML,
    to_source=to_source,
)
