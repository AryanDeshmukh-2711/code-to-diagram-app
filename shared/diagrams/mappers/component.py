"""CPM -> PlantUML component diagram, from cpm.components[].

Interfaces are drawn once and wired twice. A component that *provides* an
interface owns it (a solid line to the lollipop); a component that *requires*
it depends on it (a dashed arrow). Drawing one interface per provider would
show two unrelated circles where the model describes one contract, and would
hide the dependency that is the whole point of the diagram.

An interface nobody provides is still drawn, marked, because a requirement
with no supplier is a real gap in the design and silently omitting it makes
the diagram agree with a model that does not hold together.
"""

from cpm.schema import CPM
from diagrams.mapper import DiagramMapper, InsufficientModelData
from diagrams.text import alias, quote
from diagrams.types import Engine

_HEADER = [
    "@startuml",
    "!theme plain",
    "skinparam shadowing false",
    "skinparam componentStyle rectangle",
    "",
]


def to_source(cpm: CPM) -> str:
    if not cpm.components:
        raise InsufficientModelData(
            "No components were described, so there is no component diagram to "
            "draw. Describe the parts your system is built from — a web client, "
            "an API, a database — and what each one offers or needs."
        )

    lines = list(_HEADER)

    for component in cpm.components:
        stereotype = f" <<{component.type}>>" if component.type else ""
        lines.append(f"component {quote(component.name)} as {alias(component.id)}{stereotype}")

    interfaces: list[str] = []
    for component in cpm.components:
        for name in list(component.provides) + list(component.requires):
            if name not in interfaces:
                interfaces.append(name)

    if interfaces:
        lines.append("")
        for name in interfaces:
            lines.append(f"interface {quote(name)} as {alias('iface-' + name)}")

    lines.append("")
    for component in cpm.components:
        for name in component.provides:
            lines.append(f"{alias(component.id)} -- {alias('iface-' + name)}")
    for component in cpm.components:
        for name in component.requires:
            lines.append(f"{alias(component.id)} ..> {alias('iface-' + name)} : uses")

    provided = {name for component in cpm.components for name in component.provides}
    orphans = [name for name in interfaces if name not in provided]
    if orphans:
        lines.append("")
        for name in orphans:
            lines.append(
                f"note bottom of {alias('iface-' + name)} : no component in the model provides this"
            )

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


MAPPER = DiagramMapper(
    diagram_type="component",
    title="Component Diagram",
    engine=Engine.PLANTUML,
    to_source=to_source,
)
