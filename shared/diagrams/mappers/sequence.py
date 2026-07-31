"""CPM -> PlantUML sequence diagram, from cpm.flows[].

Pure function. Three things here are easy to get subtly wrong, so they are
stated rather than left to the reader:

**Participants are actors OR entities.** A flow's participant list mixes them,
and the CPM lets an actor and an entity share an id ("member" is both a person
who borrows and a record that is stored). Actors are looked up first, so the
lifeline for a shared id is drawn as a stick figure — which is what a reader
expects when a person sends the first message.

**One diagram, several flows.** The mapper contract is one source per diagram
type, and a CPM usually holds more than one flow. They are separated by
PlantUML dividers rather than being silently truncated to the first, or
smeared into one unreadable run of messages.

**Declaration order is layout.** Lifelines appear left to right in declaration
order, so participants are declared in first-appearance order across the flows
rather than sorted — a sequence diagram sorted alphabetically reads as a zigzag.
"""

from cpm.schema import CPM
from diagrams.mapper import DiagramMapper, InsufficientModelData
from diagrams.text import alias, quote
from diagrams.types import Engine

_HEADER = [
    "@startuml",
    "!theme plain",
    "skinparam shadowing false",
    "skinparam sequenceMessageAlign left",
    "autonumber",
    "",
]


def _participant_order(cpm: CPM) -> list[str]:
    """Every participant, in the order a reader first meets it."""
    seen: list[str] = []
    for flow in cpm.flows:
        for participant in flow.participants:
            if participant not in seen:
                seen.append(participant)
    return seen


def to_source(cpm: CPM) -> str:
    if not cpm.flows:
        raise InsufficientModelData(
            "No interaction flows were described, so there is no sequence to draw. "
            "Describe what happens step by step for a task — who does what, and "
            "what the system does in response."
        )

    actors = {actor.id: actor.name for actor in cpm.actors}
    entities = {entity.id: entity.name for entity in cpm.entities}

    lines = list(_HEADER)

    for participant in _participant_order(cpm):
        # Actors first: a shared id means the same word is both a person and a
        # record, and on a sequence diagram the person is what is meant.
        if participant in actors:
            lines.append(f"actor {quote(actors[participant])} as {alias(participant)}")
        elif participant in entities:
            lines.append(f"participant {quote(entities[participant])} as {alias(participant)}")
        else:
            # A CPM has passed referential integrity, so this cannot happen for
            # a confirmed model; falling back to the raw id beats crashing on a
            # draft being previewed.
            lines.append(f"participant {quote(participant)} as {alias(participant)}")

    lines.append("")

    for flow in cpm.flows:
        lines.append(f"== {flow.name} ==")
        for step in sorted(flow.steps, key=lambda s: (s.order, s.from_, s.to)):
            lines.append(f"{alias(step.from_)} -> {alias(step.to)} : {step.message}")
        lines.append("")

    lines.append("@enduml")
    return "\n".join(lines) + "\n"


MAPPER = DiagramMapper(
    diagram_type="sequence",
    title="Sequence Diagram",
    engine=Engine.PLANTUML,
    to_source=to_source,
)
