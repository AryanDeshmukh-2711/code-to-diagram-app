"""CPM -> Mermaid entity-relationship diagram.

Mermaid rather than PlantUML here, per SRS §8: its ER output is cleaner. Pure
function; nothing but the CPM goes in.
"""

from cpm.schema import CPM, Entity, Relationship, RelationshipType
from diagrams.mapper import DiagramMapper
from diagrams.text import er_name, er_token
from diagrams.types import Engine

# Mermaid writes the far end of the crow's foot mirrored, so these are the
# right-hand tokens. The CPM carries a single cardinality describing the target
# end, so the source end is left as "exactly one".
_TARGET_CARDINALITY: dict[str, str] = {
    "1": "||",
    "1..1": "||",
    "0..1": "o|",
    "1..*": "|{",
    "1..n": "|{",
    "0..*": "o{",
    "0..n": "o{",
    "*": "o{",
    "n": "o{",
}

_DEFAULT_TARGET_CARDINALITY = "o{"
"""Zero-or-more when the model did not say. Guessing "exactly one" would assert
a constraint nobody stated."""

# An identifying line means the child cannot exist without the parent.
_IDENTIFYING = {
    RelationshipType.COMPOSITION,
    RelationshipType.AGGREGATION,
    RelationshipType.INHERITANCE,
}


def _entity_block(entity: Entity) -> list[str]:
    lines = [f"    {er_name(entity.name)} {{"]
    for attribute in entity.attributes:
        key = " PK" if attribute.is_key else ""
        lines.append(f"        {er_token(attribute.type)} {er_token(attribute.name)}{key}")
    lines.append("    }")
    return lines


def _target_cardinality(relationship: Relationship) -> str:
    # An is-a is exactly one by construction: a Member is precisely one Person.
    # That is structural, not a constraint the description had to state, so it
    # does not fall through to the zero-or-more default.
    if relationship.type in (RelationshipType.INHERITANCE, RelationshipType.REALIZATION):
        return "||"
    return _TARGET_CARDINALITY.get(
        (relationship.cardinality or "").strip(), _DEFAULT_TARGET_CARDINALITY
    )


def _relationship_line(relationship: Relationship, names: dict[str, str]) -> str:
    target = _target_cardinality(relationship)
    line = "--" if relationship.type in _IDENTIFYING else ".."
    label = relationship.label or relationship.type.value
    return (
        f"    {er_name(names[relationship.from_])} ||{line}{target} "
        f'{er_name(names[relationship.to])} : "{label}"'
    )


def to_source(cpm: CPM) -> str:
    names = {entity.id: entity.name for entity in cpm.entities}

    lines = ["erDiagram"]
    for entity in cpm.entities:
        lines.extend(_entity_block(entity))

    for relationship in cpm.relationships:
        # A CPM has passed referential integrity, so both ends resolve.
        lines.append(_relationship_line(relationship, names))

    return "\n".join(lines) + "\n"


MAPPER = DiagramMapper(
    diagram_type="entity_relationship",
    title="Entity-Relationship Diagram",
    engine=Engine.MERMAID,
    to_source=to_source,
)
