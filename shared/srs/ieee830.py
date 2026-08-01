"""The IEEE 830-1998 section structure, populated from the CPM.

The outline is fixed by the standard, not by us — 1 Introduction, 2 Overall
Description, 3 Specific Requirements, with the subsections the standard names.
An assessor reading the table of contents should recognise it immediately, and
that recognition is a large part of what the deliverable is worth.

Two rules run through the whole file:

* Names are copied from the CPM byte for byte — not title-cased, not
  pluralised, not "tidied". FR-10 makes drift between the class diagram and
  section 3.4 a failed run, and prose is not exempt from that.
* A part of the model that is empty produces a section that says so. It never
  produces invented content, and never an empty heading with nothing under it:
  a reader cannot tell "nothing was specified" from "the generator broke", so
  the document says which.

Where a figure goes is decided by `FIGURE_PLACEMENT`, one table, keyed by the
same diagram-type string the mapper registry uses. A ninth diagram type needs
one line here — and if it does not get one it still appears, in 3.6, because
the lookup falls back rather than dropping it. FR-16 says every generated
diagram is embedded; silently losing one to a missing dictionary key is
precisely how that guarantee would rot.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from cpm.schema import CPM
from srs.ast import (
    Block,
    Document,
    DocumentMeta,
    Figure,
    FigureRef,
    ListOfFigures,
    ListOfTables,
    Section,
    SectionDraft,
    Table,
    TableOfContents,
    bullets,
    para,
    steps,
)
from srs.prose import ProseSource


@dataclass(frozen=True)
class FigureInput:
    """A rendered diagram on its way into the document.

    The SRS layer takes this rather than a `RenderedDiagram` or a database row
    so that it depends on neither the renderer nor the store: assembly is a
    pure function of a CPM plus some bytes.
    """

    diagram_type: str
    title: str
    image: bytes
    mime: str = "image/svg+xml"
    alternates: tuple[tuple[str, bytes], ...] = ()
    """The same diagram in other formats. A run rendered as both SVG and PNG
    supplies one FigureInput carrying both, so PDF can use vector and DOCX can
    use raster without the two documents being assembled separately."""

    def rendition_available(self, mime: str) -> bool:
        return mime == self.mime or any(other == mime for other, _ in self.alternates)


FIGURE_PLACEMENT: dict[str, str] = {
    "use_case": "product-functions",
    "component": "product-perspective",
    "deployment": "product-perspective",
    "sequence": "functional-requirements",
    "activity": "functional-requirements",
    "class": "design-constraints",
    "entity_relationship": "design-constraints",
    "state": "other-requirements",
}

FALLBACK_SECTION = "other-requirements"
"""A diagram type nobody placed still gets embedded, at the end. Wrong section
beats absent figure: the reader can see it, and the omission is the failure
FR-16 actually forbids."""

FIGURE_ORDER = tuple(FIGURE_PLACEMENT)
"""Fixed presentation order within a section, so identical input yields an
identical document (FR-9) regardless of the order artefacts arrived in."""

CAPTIONS = {
    "class": "Class Diagram",
    "entity_relationship": "Entity-Relationship Diagram",
    "use_case": "Use Case Diagram",
    "sequence": "Sequence Diagram",
    "activity": "Activity Diagram",
    "state": "State Diagram",
    "component": "Component Diagram",
    "deployment": "Deployment Diagram",
}


def _figure_sort_key(figure: FigureInput) -> tuple[int, str]:
    try:
        return (FIGURE_ORDER.index(figure.diagram_type), figure.diagram_type)
    except ValueError:
        return (len(FIGURE_ORDER), figure.diagram_type)


def _caption(figure: FigureInput, project: str) -> str:
    name = CAPTIONS.get(figure.diagram_type, figure.title)
    return f"{name} — {project}"


def _figure_blocks(figures: Sequence[FigureInput], section_id: str, project: str) -> list[Block]:
    return [
        Figure(
            figure_id=f"fig-{figure.diagram_type}",
            caption=_caption(figure, project),
            image=figure.image,
            mime=figure.mime,
            alt=f"{CAPTIONS.get(figure.diagram_type, figure.title)} for {project}",
            diagram_type=figure.diagram_type,
            alternates=figure.alternates,
        )
        for figure in sorted(figures, key=_figure_sort_key)
        if FIGURE_PLACEMENT.get(figure.diagram_type, FALLBACK_SECTION) == section_id
    ]


def _ref(figures: Sequence[FigureInput], diagram_type: str) -> FigureRef | None:
    """A cross-reference, but only to a figure the document actually has."""
    if any(figure.diagram_type == diagram_type for figure in figures):
        return FigureRef(target_id=f"fig-{diagram_type}")
    return None


async def build_document(
    cpm: CPM,
    figures: Sequence[FigureInput],
    prose: ProseSource,
    *,
    cpm_version_id: str | None = None,
    run_id: str | None = None,
) -> Document:
    """The whole SRS as an un-numbered tree. Numbering is a separate pass."""
    project = cpm.meta.project_name
    by_id = {actor.id: actor.name for actor in cpm.actors}

    async def written(key: str) -> str:
        return await prose.write(key, cpm)

    # -- 1 Introduction ----------------------------------------------------
    introduction = SectionDraft("introduction", "Introduction")
    introduction.sub("purpose", "Purpose").add(para(await written("purpose")))
    introduction.sub("scope", "Scope").add(para(await written("scope")))

    definitions = introduction.sub("definitions", "Definitions, Acronyms and Abbreviations")
    terms = [(actor.name, "Actor", actor.description) for actor in cpm.actors]
    terms += [(entity.name, "Entity", entity.description) for entity in cpm.entities]
    if terms:
        definitions.add(
            Table(
                table_id="tbl-glossary",
                caption="Terms used in this specification",
                columns=("Term", "Kind", "Description"),
                rows=tuple(
                    (name, kind, description or "No description recorded in the model.")
                    for name, kind, description in terms
                ),
            )
        )
    else:
        definitions.add(para("The model defines no named terms."))

    introduction.sub("references", "References").add(
        bullets(
            [
                "IEEE Std 830-1998, IEEE Recommended Practice for Software "
                "Requirements Specifications.",
                "OMG Unified Modeling Language (OMG UML), Version 2.5.1.",
                f"{project} project model, version {cpm.meta.version}, as confirmed "
                f"at the review stage.",
            ]
        )
    )
    introduction.sub("overview", "Overview").add(para(await written("overview")))

    # -- 2 Overall Description --------------------------------------------
    overall = SectionDraft("overall-description", "Overall Description")

    perspective = overall.sub("product-perspective", "Product Perspective")
    perspective.add(para(await written("product_perspective")))
    if cpm.components:
        perspective.add(
            Table(
                table_id="tbl-components",
                caption="System components",
                columns=("Component", "Type", "Provides", "Requires"),
                rows=tuple(
                    (
                        component.name,
                        component.type,
                        ", ".join(component.provides) or "—",
                        ", ".join(component.requires) or "—",
                    )
                    for component in cpm.components
                ),
            )
        )
    perspective.add(*_figure_blocks(figures, "product-perspective", project))

    functions = overall.sub("product-functions", "Product Functions")
    functions.add(para(await written("product_functions")))
    if cpm.use_cases:
        functions.add(bullets([use_case.name for use_case in cpm.use_cases]))
    reference = _ref(figures, "use_case")
    if reference is not None:
        functions.add(para("These functions and their actors are shown in ", reference, "."))
    functions.add(*_figure_blocks(figures, "product-functions", project))

    characteristics = overall.sub("user-characteristics", "User Characteristics")
    characteristics.add(para(await written("user_characteristics")))
    if cpm.actors:
        characteristics.add(
            Table(
                table_id="tbl-actors",
                caption="User classes",
                columns=("Actor", "Role", "Description"),
                rows=tuple(
                    (
                        actor.name,
                        "Primary" if actor.is_primary else "Secondary",
                        actor.description or "No description recorded in the model.",
                    )
                    for actor in cpm.actors
                ),
            )
        )

    constraints = overall.sub("constraints", "Constraints")
    constraints.add(para(await written("constraints")))
    non_functional = [r for r in cpm.requirements if r.type == "nonFunctional"]
    if non_functional:
        constraints.add(bullets([f"{r.id}: {r.text}" for r in non_functional]))

    overall.sub("assumptions", "Assumptions and Dependencies").add(
        para(await written("assumptions"))
    )

    # -- 3 Specific Requirements ------------------------------------------
    specific = SectionDraft("specific-requirements", "Specific Requirements")

    interfaces = specific.sub("external-interfaces", "External Interface Requirements")
    interfaces.add(para(await written("external_interfaces")))
    required = [component for component in cpm.components if component.requires]
    if required:
        interfaces.add(
            bullets(
                [
                    f"{component.name} requires {', '.join(component.requires)}."
                    for component in required
                ]
            )
        )

    functional = specific.sub("functional-requirements", "Functional Requirements")
    functional.add(para(await written("functional_requirements")))
    functional_requirements = [r for r in cpm.requirements if r.type == "functional"]
    if functional_requirements:
        functional.add(
            Table(
                table_id="tbl-functional",
                caption="Functional requirements",
                columns=("ID", "Requirement", "Priority"),
                rows=tuple(
                    (r.id, r.text, r.priority or "Unspecified") for r in functional_requirements
                ),
            )
        )
    for use_case in cpm.use_cases:
        detail = functional.sub(f"uc-{use_case.id}", use_case.name)
        actors = [by_id[actor_id] for actor_id in use_case.actors if actor_id in by_id]
        detail.add(
            para(f"Actors: {', '.join(actors) if actors else 'none recorded in the model'}.")
        )
        detail.add(
            para("Preconditions:"),
            bullets(use_case.preconditions)
            if use_case.preconditions
            else para("None recorded in the model."),
        )
        detail.add(
            para("Main flow:"),
            steps(use_case.main_flow)
            if use_case.main_flow
            else para("No main flow recorded in the model."),
        )
        if use_case.alternate_flows:
            detail.add(para("Alternate flows:"), bullets(use_case.alternate_flows))
        detail.add(
            para("Postconditions:"),
            bullets(use_case.postconditions)
            if use_case.postconditions
            else para("None recorded in the model."),
        )
    if cpm.flows:
        reference = _ref(figures, "sequence")
        if reference is not None:
            functional.add(
                para(
                    "The interactions between participants for these functions are shown in ",
                    reference,
                    ".",
                )
            )
    functional.add(*_figure_blocks(figures, "functional-requirements", project))

    performance = specific.sub("performance-requirements", "Performance Requirements")
    performance.add(para(await written("performance")))

    design = specific.sub("design-constraints", "Design Constraints")
    design.add(para(await written("design_constraints")))
    for entity in cpm.entities:
        if not entity.attributes:
            continue
        design.add(
            Table(
                table_id=f"tbl-entity-{entity.id}",
                caption=f"Attributes of {entity.name}",
                columns=("Attribute", "Type", "Key", "Required"),
                rows=tuple(
                    (
                        attribute.name,
                        attribute.type,
                        "Yes" if attribute.is_key else "No",
                        "Yes" if attribute.is_required else "No",
                    )
                    for attribute in entity.attributes
                ),
            )
        )
    if cpm.relationships:
        names = {entity.id: entity.name for entity in cpm.entities}
        names.update(by_id)
        design.add(
            Table(
                table_id="tbl-relationships",
                caption="Relationships between entities",
                columns=("From", "To", "Type", "Cardinality", "Label"),
                rows=tuple(
                    (
                        names.get(relationship.from_, relationship.from_),
                        names.get(relationship.to, relationship.to),
                        str(relationship.type),
                        relationship.cardinality or "—",
                        relationship.label or "—",
                    )
                    for relationship in cpm.relationships
                ),
            )
        )
    design.add(*_figure_blocks(figures, "design-constraints", project))

    attributes = specific.sub("system-attributes", "Software System Attributes")
    attributes.add(para(await written("attributes")))
    if non_functional:
        attributes.add(
            Table(
                table_id="tbl-nonfunctional",
                caption="Non-functional requirements",
                columns=("ID", "Requirement", "Priority"),
                rows=tuple((r.id, r.text, r.priority or "Unspecified") for r in non_functional),
            )
        )
    else:
        attributes.add(para("The model records no non-functional requirements."))

    other = specific.sub("other-requirements", "Other Requirements")
    other.add(para(await written("other")))
    if cpm.states:
        entity_names = {entity.id: entity.name for entity in cpm.entities}
        other.add(
            Table(
                table_id="tbl-states",
                caption="Lifecycle states",
                columns=("Entity", "State", "Initial", "Final", "Transitions"),
                rows=tuple(
                    (
                        entity_names.get(state.entity_ref, state.entity_ref),
                        state.name,
                        "Yes" if state.is_initial else "No",
                        "Yes" if state.is_final else "No",
                        str(len(state.transitions)),
                    )
                    for state in cpm.states
                ),
            )
        )
    other.add(*_figure_blocks(figures, "other-requirements", project))

    return Document(
        title=f"Software Requirements Specification — {project}",
        meta=DocumentMeta(
            project_name=project,
            version=cpm.meta.version,
            authors=tuple(cpm.meta.authors),
            created_at=cpm.meta.created_at.isoformat() if cpm.meta.created_at else None,
            cpm_version_id=cpm_version_id,
            run_id=run_id,
        ),
        front_matter=(TableOfContents(), ListOfFigures(), ListOfTables()),
        sections=_built(introduction, overall, specific),
    )


def _built(*drafts: SectionDraft) -> tuple[Section, ...]:
    return tuple(draft.build() for draft in drafts)
