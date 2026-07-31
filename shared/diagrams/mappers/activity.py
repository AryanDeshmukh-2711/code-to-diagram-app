"""CPM -> PlantUML activity diagram, from cpm.useCases[].

Built from the main flow, which is the only part of a use case that is a
sequence of actions. Preconditions and postconditions bracket it as notes
rather than becoming steps: "the member is registered" is a condition that
holds, not something anybody does, and drawing it as an action would put a
box in the flow that nothing ever performs.

Alternate flows become explicit branches off the end of the main path. The CPM
records them as prose rather than as attachment points, so they are drawn where
they are certainly true — after the main flow — instead of guessing which step
each one interrupts. Guessing would produce a diagram that is confidently wrong
about the control flow, which is worse than one that is visibly conservative.

One swimlane per use case: a CPM holds several, and a single start-to-stop
activity for all of them would imply they run in sequence.
"""

from cpm.schema import CPM
from diagrams.mapper import DiagramMapper, InsufficientModelData
from diagrams.text import quote
from diagrams.types import Engine

_HEADER = [
    "@startuml",
    "!theme plain",
    "skinparam shadowing false",
    "skinparam activityDiamondBackgroundColor White",
    "",
]


def _step(text: str) -> str:
    """One action. Semicolons end an activity in PlantUML, so any inside the
    text would truncate the box."""
    return f":{text.replace(';', ',')};"


def to_source(cpm: CPM) -> str:
    usable = [use_case for use_case in cpm.use_cases if use_case.main_flow]
    if not usable:
        raise InsufficientModelData(
            "No use case describes a main flow, so there is nothing to draw as an "
            "activity. Describe the steps of a task in order — what the user does "
            "and what the system does in response."
        )

    lines = list(_HEADER)

    for use_case in usable:
        lines.append(f"partition {quote(use_case.name)} {{")
        lines.append("  start")

        for condition in use_case.preconditions:
            lines.append(f"  note right: precondition — {condition}")

        for action in use_case.main_flow:
            lines.append(f"  {_step(action)}")

        for alternate in use_case.alternate_flows:
            # A branch, not a step: an alternate flow is a different outcome,
            # and drawing it inline would claim it always happens.
            lines.append("  if (alternate path?) then (yes)")
            lines.append(f"    {_step(alternate)}")
            lines.append("  endif")

        for condition in use_case.postconditions:
            lines.append(f"  note right: postcondition — {condition}")

        lines.append("  stop")
        lines.append("}")
        lines.append("")

    lines.append("@enduml")
    return "\n".join(lines) + "\n"


MAPPER = DiagramMapper(
    diagram_type="activity",
    title="Activity Diagram",
    engine=Engine.PLANTUML,
    to_source=to_source,
)
