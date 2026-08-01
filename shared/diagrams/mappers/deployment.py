"""CPM -> PlantUML deployment diagram, from cpm.nodes[].

Components are drawn *inside* the node that runs them, because that nesting is
the only thing a deployment diagram says that a component diagram does not. A
flat list of boxes with association lines would be a component diagram with
different labels.

A component the model never places on a node is drawn outside them, marked. It
is a real hole — something in the design has nowhere to run — and a diagram
that omits it agrees with a model that does not hold together.
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
    if not cpm.nodes:
        raise InsufficientModelData(
            "No deployment nodes were described, so there is no deployment "
            "diagram to draw. Describe where the parts of your system run — a "
            "browser, an application server, a database host."
        )

    components = {component.id: component.name for component in cpm.components}

    lines = list(_HEADER)
    placed: set[str] = set()

    for node in cpm.nodes:
        stereotype = f" <<{node.type}>>" if node.type else ""
        lines.append(f"node {quote(node.name)} as {alias(node.id)}{stereotype} {{")
        for component_id in node.deployed_components:
            placed.add(component_id)
            name = components.get(component_id, component_id)
            lines.append(f"  component {quote(name)} as {alias(component_id)}")
        if not node.deployed_components:
            lines.append("  ' nothing in the model is deployed here")
        lines.append("}")
        lines.append("")

    homeless = [c for c in cpm.components if c.id not in placed]
    if homeless:
        for component in homeless:
            lines.append(f"component {quote(component.name)} as {alias(component.id)}")
            lines.append(
                f"note bottom of {alias(component.id)} : the model does not say where this runs"
            )
        lines.append("")

    for node_index, node in enumerate(cpm.nodes[:-1]):
        # Nodes are wired in declaration order: the model records what runs
        # where, not the topology between hosts, and inventing links between
        # them would be inventing architecture.
        lines.append(f"{alias(node.id)} -- {alias(cpm.nodes[node_index + 1].id)}")

    lines.append("")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


MAPPER = DiagramMapper(
    diagram_type="deployment",
    title="Deployment Diagram",
    engine=Engine.PLANTUML,
    to_source=to_source,
)
