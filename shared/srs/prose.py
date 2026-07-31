"""Narrative sections: written from the CPM, by rule or by model.

Two implementations behind one interface.

`DeterministicProse` composes sentences from CPM facts. It is the default, and
that is a deliberate product choice rather than a stopgap: it is free, it is
instant, it is reproducible run to run (FR-9), and it cannot invent a
requirement that nobody stated. For an SRS whose value is being *accurate and
submittable*, that covers most of what the prose has to do.

`GatewayProse` sends the CPM — and nothing else — through the LLM Gateway. Two
constraints are structural, not conventions:

* The only input is the confirmed CPM. Never the user's original upload, never
  a previous draft, never free text a caller supplies. So a prose section
  cannot introduce a fact that is not in the model, which is what keeps C-3
  true — every artefact still derives from the CPM.
* Whatever comes back is passed through the FR-10 name check before it is
  allowed into the document. A model writing "the Books table" when the entity
  is `Book` has broken the one guarantee the product is sold on, and prose is
  no more exempt from that than a diagram is.

The section key travels in the payload rather than in the prompt, and it comes
from `SECTIONS` here — never from a caller's string — so a call site still
cannot re-task the model. That is the same rule the gateway's system prompts
enforce, applied one level up.
"""

import json
import logging
from typing import Protocol

from pydantic import BaseModel, Field

from cpm.schema import CPM

logger = logging.getLogger(__name__)

TASK = "srs_prose"

SECTIONS: dict[str, str] = {
    "purpose": "1.1 Purpose — what this document specifies and who it is for.",
    "scope": "1.2 Scope — what the software does, and what it does not do.",
    "overview": "1.5 Overview — how the rest of this document is organised.",
    "product_perspective": "2.1 Product Perspective — how the system sits among its components.",
    "product_functions": "2.2 Product Functions — a summary of what the system does.",
    "user_characteristics": "2.3 User Characteristics — who uses the system.",
    "constraints": "2.4 Constraints — what limits the implementation.",
    "assumptions": "2.5 Assumptions and Dependencies — what is taken as given.",
    "external_interfaces": "3.1 External Interface Requirements — the boundaries.",
    "functional_requirements": "3.2 Functional Requirements — what the system shall do.",
    "performance": "3.3 Performance Requirements — required speed and capacity.",
    "design_constraints": "3.4 Design Constraints — the data and structure the design must honour.",
    "attributes": "3.5 Software System Attributes — reliability, security, maintainability.",
    "other": "3.6 Other Requirements — everything the model records that is not above.",
}
"""The complete set of narrative sections. A key not in here cannot be asked
for, from either implementation."""


class UnknownProseSection(KeyError):
    pass


class ProseSource(Protocol):
    async def write(self, key: str, cpm: CPM) -> str: ...


class ProseOut(BaseModel):
    text: str = Field(min_length=1)


def _check(key: str) -> None:
    if key not in SECTIONS:
        raise UnknownProseSection(f"{key!r} is not an SRS prose section; known: {sorted(SECTIONS)}")


# ---------------------------------------------------------------------------
# Deterministic
# ---------------------------------------------------------------------------


def _join(names: list[str], conjunction: str = "and") -> str:
    """An Oxford-comma list. Names are inserted verbatim — never pluralised,
    never title-cased — because every one of them is under FR-10."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} {conjunction} {names[1]}"
    return ", ".join(names[:-1]) + f", {conjunction} {names[-1]}"


class DeterministicProse:
    """Sentences composed from the model. No network, no cost, no invention."""

    async def write(self, key: str, cpm: CPM) -> str:
        _check(key)
        return getattr(self, f"_{key}")(cpm)

    def _purpose(self, cpm: CPM) -> str:
        return (
            f"This document specifies the software requirements for "
            f"{cpm.meta.project_name}. It is intended for the developers, "
            f"reviewers and assessors of the system, and it describes what the "
            f"system is required to do rather than how it is to be built. "
            f"The specification follows the IEEE 830-1998 recommended practice."
        )

    def _scope(self, cpm: CPM) -> str:
        description = (cpm.meta.description or "").strip()
        opening = f"{cpm.meta.project_name} is a software system"
        if description:
            opening = f"{opening} described as follows: {description}"
        entity_names = [entity.name for entity in cpm.entities]
        actor_names = [actor.name for actor in cpm.actors]
        parts = [opening + "."]
        if entity_names:
            parts.append(f"The system maintains information about {_join(entity_names)}.")
        if actor_names:
            parts.append(f"It is used by {_join(actor_names)}.")
        parts.append(
            "Anything not stated in this specification is outside the scope of "
            "the system as specified."
        )
        return " ".join(parts)

    def _overview(self, cpm: CPM) -> str:
        return (
            "The remainder of this document is organised as follows. Section 2 "
            "gives an overall description of the product, its functions, its "
            "users and the constraints under which it operates. Section 3 states "
            "the specific requirements in detail, together with the models that "
            "define the system's structure and behaviour. Figures are numbered "
            "sequentially and listed after the table of contents."
        )

    def _product_perspective(self, cpm: CPM) -> str:
        if not cpm.components:
            return (
                f"{cpm.meta.project_name} is a self-contained system. The model "
                f"records no separate components, so the system is specified here "
                f"as a single deployable unit."
            )
        names = [component.name for component in cpm.components]
        sentence = f"{cpm.meta.project_name} is composed of {_join(names)}."
        provided = [c for c in cpm.components if c.provides]
        if provided:
            sentence += (
                f" {provided[0].name} provides "
                f"{_join(list(provided[0].provides))}"
                f"{'.' if len(provided) == 1 else ', among other interfaces.'}"
            )
        if cpm.nodes:
            sentence += f" The system is deployed across {_join([n.name for n in cpm.nodes])}."
        return sentence

    def _product_functions(self, cpm: CPM) -> str:
        if not cpm.use_cases:
            return (
                "The model records no use cases, so no product functions are "
                "specified. This section is intentionally empty rather than "
                "filled with assumed behaviour."
            )
        return (
            f"The system supports {len(cpm.use_cases)} principal function"
            f"{'' if len(cpm.use_cases) == 1 else 's'}, summarised below and "
            f"specified in full in Section 3.2."
        )

    def _user_characteristics(self, cpm: CPM) -> str:
        if not cpm.actors:
            return "The model records no actors, so no user classes are specified."
        primary = [actor.name for actor in cpm.actors if actor.is_primary]
        text = (
            f"{len(cpm.actors)} user class"
            f"{'' if len(cpm.actors) == 1 else 'es'} interact with the system."
        )
        if primary:
            text += f" {_join(primary)} initiate the system's principal functions."
        return text

    def _constraints(self, cpm: CPM) -> str:
        constraints = [r for r in cpm.requirements if r.type == "nonFunctional"]
        if not constraints:
            return (
                "The model records no non-functional constraints. The "
                "implementation is therefore unconstrained by this specification "
                "beyond the requirements stated in Section 3."
            )
        return (
            f"The implementation is subject to {len(constraints)} non-functional "
            f"requirement{'' if len(constraints) == 1 else 's'}, listed in "
            f"Section 3.3 and Section 3.5."
        )

    def _assumptions(self, cpm: CPM) -> str:
        return (
            "This specification assumes that the structured model from which it "
            "was generated has been reviewed and confirmed as an accurate "
            "description of the intended system. Every requirement, diagram and "
            "table in this document derives from that model; nothing in it was "
            "introduced afterwards."
        )

    def _external_interfaces(self, cpm: CPM) -> str:
        required = [c for c in cpm.components if c.requires]
        if not required:
            return (
                "The model records no external interfaces. The system as "
                "specified does not depend on an interface outside its own "
                "boundary."
            )
        return (
            f"{len(required)} component"
            f"{'' if len(required) == 1 else 's'} of the system depend"
            f"{'s' if len(required) == 1 else ''} on interfaces provided "
            f"elsewhere. These are listed below."
        )

    def _functional_requirements(self, cpm: CPM) -> str:
        return (
            "Each function below is specified by its actors, its preconditions, "
            "the main flow of events, any alternate flows, and the "
            "postconditions that hold once it completes."
        )

    def _performance(self, cpm: CPM) -> str:
        performance = [
            r
            for r in cpm.requirements
            if r.type == "nonFunctional"
            and any(
                word in r.text.lower()
                for word in ("second", "concurrent", "throughput", "load", "response")
            )
        ]
        if not performance:
            return (
                "The model states no performance requirements. None are invented "
                "here; a performance figure that nobody specified is not a "
                "requirement."
            )
        return (
            f"{len(performance)} performance requirement"
            f"{'' if len(performance) == 1 else 's'} apply to the system."
        )

    def _design_constraints(self, cpm: CPM) -> str:
        return (
            f"The structure of the system's data is fixed by the model below. "
            f"{len(cpm.entities)} entit"
            f"{'y is' if len(cpm.entities) == 1 else 'ies are'} specified, related "
            f"by {len(cpm.relationships)} relationship"
            f"{'' if len(cpm.relationships) == 1 else 's'}. The implementation "
            f"shall preserve these entities, their attributes and their "
            f"relationships."
        )

    def _attributes(self, cpm: CPM) -> str:
        return (
            "The following non-functional requirements govern the reliability, "
            "security, portability and maintainability of the system."
        )

    def _other(self, cpm: CPM) -> str:
        if cpm.states:
            entities = sorted({state.entity_ref for state in cpm.states})
            return (
                f"The model specifies lifecycle states for "
                f"{len(entities)} entit{'y' if len(entities) == 1 else 'ies'}. "
                f"An implementation shall permit only the transitions defined below."
            )
        return "The model records no further requirements."


# ---------------------------------------------------------------------------
# Model-written
# ---------------------------------------------------------------------------


class GatewayProse:
    """Prose from the LLM Gateway, with the CPM as its only input.

    A failure is not swallowed. If the model is unreachable, times out or
    returns something unusable, `write` raises and assembly stops — falling
    back to deterministic text on the quiet would mean a document whose voice
    changes halfway through for reasons the user never sees, and would hide a
    broken deployment behind output that looks fine.
    """

    def __init__(self, gateway, user_id: str | None = None) -> None:
        self._gateway = gateway
        self._user_id = user_id

    async def write(self, key: str, cpm: CPM) -> str:
        _check(key)
        payload = json.dumps(
            {
                "section": key,
                "sectionDescription": SECTIONS[key],
                "model": cpm.model_dump(by_alias=True, mode="json"),
            },
            sort_keys=True,
        )
        result = await self._gateway.complete(TASK, payload, ProseOut, user_id=self._user_id)
        return result.text.strip()
