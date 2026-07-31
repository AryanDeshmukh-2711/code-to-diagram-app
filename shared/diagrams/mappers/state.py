"""CPM -> PlantUML state diagram, from cpm.states[].

Grouped by `entityRef`, because a state machine belongs to a thing. A CPM
usually describes lifecycles for two or three entities, and flattening them
into one machine would draw transitions between states that can never meet —
a Loan cannot become "Collected", and a diagram that suggests it can is worse
than no diagram.

Composite states are how PlantUML expresses that grouping, so each entity gets
one, with its own initial and final pseudo-states inside it.
"""

from cpm.schema import CPM
from diagrams.mapper import DiagramMapper, InsufficientModelData
from diagrams.text import alias, quote
from diagrams.types import Engine

_HEADER = [
    "@startuml",
    "!theme plain",
    "skinparam shadowing false",
    "skinparam state {",
    "  BackgroundColor White",
    "}",
    "",
]


def to_source(cpm: CPM) -> str:
    if not cpm.states:
        raise InsufficientModelData(
            "No lifecycle states were described, so there is no state machine to "
            "draw. Describe the stages something in your system passes through — "
            "for example a loan being active, overdue, then closed."
        )

    entities = {entity.id: entity.name for entity in cpm.entities}

    grouped: dict[str, list] = {}
    for state in cpm.states:
        grouped.setdefault(state.entity_ref, []).append(state)

    lines = list(_HEADER)

    for entity_ref in sorted(grouped):
        states = grouped[entity_ref]
        owner = entities.get(entity_ref, entity_ref)
        lines.append(f"state {quote(owner)} as {alias(entity_ref)} {{")

        for state in states:
            lines.append(f"  state {quote(state.name)} as {alias(state.id)}")

        for state in states:
            if state.is_initial:
                lines.append(f"  [*] --> {alias(state.id)}")

        for state in states:
            for transition in state.transitions:
                # UML writes a guard beside its trigger, not after a second
                # colon: "returned [fine settled]", not "returned : [fine settled]".
                label = " ".join(
                    part
                    for part in (
                        transition.trigger,
                        f"[{transition.guard}]" if transition.guard else "",
                    )
                    if part
                )
                arrow = f"  {alias(state.id)} --> {alias(transition.to)}"
                lines.append(f"{arrow} : {label}" if label else arrow)

        for state in states:
            if state.is_final:
                lines.append(f"  {alias(state.id)} --> [*]")

        lines.append("}")
        lines.append("")

    lines.append("@enduml")
    return "\n".join(lines) + "\n"


MAPPER = DiagramMapper(
    diagram_type="state",
    title="State Diagram",
    engine=Engine.PLANTUML,
    to_source=to_source,
)
