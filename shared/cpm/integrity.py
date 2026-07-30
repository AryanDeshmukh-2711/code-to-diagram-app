"""Referential integrity checks over a CPM draft.

Returns a list rather than raising on the first problem: the review gate needs
to show the user everything that is wrong at once, not make them fix and
resubmit ten times.

Ids are unique **per collection**, not globally. "Member" is legitimately both
an actor and an entity in most domain models, so a global uniqueness rule would
reject correct input. Every reference is typed, so per-collection uniqueness is
enough to resolve one unambiguously.
"""

from dataclasses import dataclass
from enum import StrEnum

from cpm.schema import CPMDraft


class IntegrityCode(StrEnum):
    DUPLICATE_ID = "duplicate_id"
    DUPLICATE_ENTITY_NAME = "duplicate_entity_name"
    DUPLICATE_ACTOR_NAME = "duplicate_actor_name"
    UNKNOWN_ENTITY_REF = "unknown_entity_ref"
    UNKNOWN_ACTOR_REF = "unknown_actor_ref"
    UNKNOWN_COMPONENT_REF = "unknown_component_ref"
    UNKNOWN_PARTICIPANT_REF = "unknown_participant_ref"
    STEP_ENDPOINT_NOT_A_PARTICIPANT = "step_endpoint_not_a_participant"
    UNKNOWN_STATE_REF = "unknown_state_ref"
    STATE_TRANSITION_CROSSES_ENTITY = "state_transition_crosses_entity"
    DUPLICATE_STEP_ORDER = "duplicate_step_order"


@dataclass(frozen=True)
class IntegrityIssue:
    """One violation.

    ``path`` is a camelCase JSON path (e.g. ``relationships[2].from``) so the
    review-gate UI can highlight the exact field the user has to fix.
    """

    code: IntegrityCode
    path: str
    message: str
    offending_id: str | None = None


def _name_key(name: str) -> str:
    """Normalise a name for duplicate detection.

    Case-folded and internally whitespace-collapsed, because "Book" / "book" /
    "Book  Copy" are the duplicates LLM extraction actually produces, and
    byte-identical naming downstream (FR-10) is impossible if both survive.
    """
    return " ".join(name.split()).casefold()


def _collections(model: CPMDraft) -> list[tuple[str, list]]:
    """Every id-bearing collection, paired with its camelCase JSON name."""
    return [
        ("actors", list(model.actors)),
        ("entities", list(model.entities)),
        ("relationships", list(model.relationships)),
        ("useCases", list(model.use_cases)),
        ("flows", list(model.flows)),
        ("states", list(model.states)),
        ("components", list(model.components)),
        ("nodes", list(model.nodes)),
        ("requirements", list(model.requirements)),
    ]


def _check_duplicate_ids(model: CPMDraft) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    for collection, items in _collections(model):
        first_seen: dict[str, int] = {}
        for index, item in enumerate(items):
            if item.id in first_seen:
                issues.append(
                    IntegrityIssue(
                        code=IntegrityCode.DUPLICATE_ID,
                        path=f"{collection}[{index}].id",
                        message=(
                            f"id {item.id!r} is already used by {collection}[{first_seen[item.id]}]"
                        ),
                        offending_id=item.id,
                    )
                )
            else:
                first_seen[item.id] = index
    return issues


def _check_duplicate_names(model: CPMDraft) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    for collection, items, code in (
        ("entities", list(model.entities), IntegrityCode.DUPLICATE_ENTITY_NAME),
        ("actors", list(model.actors), IntegrityCode.DUPLICATE_ACTOR_NAME),
    ):
        first_seen: dict[str, int] = {}
        for index, item in enumerate(items):
            key = _name_key(item.name)
            if key in first_seen:
                issues.append(
                    IntegrityIssue(
                        code=code,
                        path=f"{collection}[{index}].name",
                        message=(
                            f"name {item.name!r} duplicates "
                            f"{collection}[{first_seen[key]}] (comparison ignores case "
                            f"and repeated whitespace)"
                        ),
                        offending_id=item.id,
                    )
                )
            else:
                first_seen[key] = index
    return issues


def _check_relationships(model: CPMDraft, entity_ids: set[str]) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    for index, relationship in enumerate(model.relationships):
        for field, value in (("from", relationship.from_), ("to", relationship.to)):
            if value not in entity_ids:
                issues.append(
                    IntegrityIssue(
                        code=IntegrityCode.UNKNOWN_ENTITY_REF,
                        path=f"relationships[{index}].{field}",
                        message=(
                            f"relationship {relationship.id!r} points at unknown entity {value!r}"
                        ),
                        offending_id=value,
                    )
                )
    return issues


def _check_use_cases(model: CPMDraft, actor_ids: set[str]) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    for index, use_case in enumerate(model.use_cases):
        for position, actor_id in enumerate(use_case.actors):
            if actor_id not in actor_ids:
                issues.append(
                    IntegrityIssue(
                        code=IntegrityCode.UNKNOWN_ACTOR_REF,
                        path=f"useCases[{index}].actors[{position}]",
                        message=(f"use case {use_case.id!r} references unknown actor {actor_id!r}"),
                        offending_id=actor_id,
                    )
                )
    return issues


def _check_states(model: CPMDraft, entity_ids: set[str]) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    state_entity_by_id = {state.id: state.entity_ref for state in model.states}

    for index, state in enumerate(model.states):
        if state.entity_ref not in entity_ids:
            issues.append(
                IntegrityIssue(
                    code=IntegrityCode.UNKNOWN_ENTITY_REF,
                    path=f"states[{index}].entityRef",
                    message=f"state {state.id!r} belongs to unknown entity {state.entity_ref!r}",
                    offending_id=state.entity_ref,
                )
            )

        for position, transition in enumerate(state.transitions):
            path = f"states[{index}].transitions[{position}].to"
            if transition.to not in state_entity_by_id:
                issues.append(
                    IntegrityIssue(
                        code=IntegrityCode.UNKNOWN_STATE_REF,
                        path=path,
                        message=f"state {state.id!r} transitions to unknown state "
                        f"{transition.to!r}",
                        offending_id=transition.to,
                    )
                )
            elif state_entity_by_id[transition.to] != state.entity_ref:
                # A state machine is drawn per entity, so a transition leaving
                # that entity has nowhere to be rendered.
                issues.append(
                    IntegrityIssue(
                        code=IntegrityCode.STATE_TRANSITION_CROSSES_ENTITY,
                        path=path,
                        message=(
                            f"state {state.id!r} (entity {state.entity_ref!r}) transitions to "
                            f"{transition.to!r}, which belongs to entity "
                            f"{state_entity_by_id[transition.to]!r}"
                        ),
                        offending_id=transition.to,
                    )
                )
    return issues


def _check_nodes(model: CPMDraft, component_ids: set[str]) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    for index, node in enumerate(model.nodes):
        for position, component_id in enumerate(node.deployed_components):
            if component_id not in component_ids:
                issues.append(
                    IntegrityIssue(
                        code=IntegrityCode.UNKNOWN_COMPONENT_REF,
                        path=f"nodes[{index}].deployedComponents[{position}]",
                        message=(f"node {node.id!r} deploys unknown component {component_id!r}"),
                        offending_id=component_id,
                    )
                )
    return issues


def _check_flows(model: CPMDraft, participant_ids: set[str]) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    for index, flow in enumerate(model.flows):
        for position, participant in enumerate(flow.participants):
            if participant not in participant_ids:
                issues.append(
                    IntegrityIssue(
                        code=IntegrityCode.UNKNOWN_PARTICIPANT_REF,
                        path=f"flows[{index}].participants[{position}]",
                        message=(
                            f"flow {flow.id!r} declares participant {participant!r}, which is "
                            f"neither an actor nor an entity"
                        ),
                        offending_id=participant,
                    )
                )

        declared = set(flow.participants)
        order_first_seen: dict[int, int] = {}

        for position, step in enumerate(flow.steps):
            for field, value in (("from", step.from_), ("to", step.to)):
                if value not in declared:
                    # A sequence diagram cannot draw a message to a lifeline
                    # that was never declared.
                    issues.append(
                        IntegrityIssue(
                            code=IntegrityCode.STEP_ENDPOINT_NOT_A_PARTICIPANT,
                            path=f"flows[{index}].steps[{position}].{field}",
                            message=(
                                f"flow {flow.id!r} step {step.order} references {value!r}, "
                                f"which is not one of its declared participants"
                            ),
                            offending_id=value,
                        )
                    )

            if step.order in order_first_seen:
                # Ties make render order depend on input order, which breaks
                # deterministic diagram source (FR-9).
                issues.append(
                    IntegrityIssue(
                        code=IntegrityCode.DUPLICATE_STEP_ORDER,
                        path=f"flows[{index}].steps[{position}].order",
                        message=(
                            f"flow {flow.id!r} reuses step order {step.order}, already used by "
                            f"step[{order_first_seen[step.order]}]"
                        ),
                    )
                )
            else:
                order_first_seen[step.order] = position
    return issues


def check_integrity(model: CPMDraft) -> list[IntegrityIssue]:
    """Every referential integrity violation in ``model``, in reporting order."""
    entity_ids = {entity.id for entity in model.entities}
    actor_ids = {actor.id for actor in model.actors}
    component_ids = {component.id for component in model.components}

    return [
        *_check_duplicate_ids(model),
        *_check_duplicate_names(model),
        *_check_relationships(model, entity_ids),
        *_check_use_cases(model, actor_ids),
        *_check_states(model, entity_ids),
        *_check_nodes(model, component_ids),
        *_check_flows(model, actor_ids | entity_ids),
    ]
