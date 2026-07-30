"""Referential integrity across the CPM.

Every artefact in the product renders from this model. A dangling reference here
becomes a diagram that fails to render, or worse, one that renders wrongly and
is submitted. Each check therefore reports a machine-readable code plus a path
the review-gate UI can point at.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from cpm.integrity import IntegrityCode, check_integrity
from cpm.schema import CPM, CPMDraft


def issues_for(payload: dict[str, Any]) -> list:
    return check_integrity(CPMDraft.model_validate(payload))


def codes_for(payload: dict[str, Any]) -> set[IntegrityCode]:
    return {issue.code for issue in issues_for(payload)}


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_fixture_has_no_integrity_issues(payload: dict[str, Any]) -> None:
    assert issues_for(payload) == []


def test_an_actor_and_an_entity_may_share_an_id_and_a_name(payload: dict[str, Any]) -> None:
    # "Member" is legitimately both a system actor and a persisted entity. Ids
    # are therefore unique per collection, NOT globally — a global uniqueness
    # rule would reject most real domain models.
    actor_ids = {actor["id"] for actor in payload["actors"]}
    entity_ids = {entity["id"] for entity in payload["entities"]}
    assert actor_ids & entity_ids, "fixture must exercise the actor/entity id overlap"
    assert issues_for(payload) == []


# --------------------------------------------------------------------------
# Uniqueness
# --------------------------------------------------------------------------


def test_duplicate_entity_id_is_reported(payload: dict[str, Any]) -> None:
    payload["entities"].append(dict(payload["entities"][0]))
    assert IntegrityCode.DUPLICATE_ID in codes_for(payload)


def test_duplicate_entity_name_is_reported(payload: dict[str, Any]) -> None:
    clone = dict(payload["entities"][0])
    clone["id"] = "book-copy"
    payload["entities"].append(clone)
    assert IntegrityCode.DUPLICATE_ENTITY_NAME in codes_for(payload)


def test_duplicate_entity_name_differing_only_by_case_is_reported(
    payload: dict[str, Any],
) -> None:
    # The exact failure mode of LLM extraction: "Book" and "book" as two
    # entities. Byte-identical naming downstream (FR-10) is impossible if both
    # survive the gate.
    clone = dict(payload["entities"][0])
    clone["id"] = "book-lower"
    clone["name"] = payload["entities"][0]["name"].lower()
    payload["entities"].append(clone)
    assert IntegrityCode.DUPLICATE_ENTITY_NAME in codes_for(payload)


def test_duplicate_actor_name_is_reported(payload: dict[str, Any]) -> None:
    clone = dict(payload["actors"][0])
    clone["id"] = "member-two"
    payload["actors"].append(clone)
    assert IntegrityCode.DUPLICATE_ACTOR_NAME in codes_for(payload)


def test_duplicate_use_case_id_is_reported(payload: dict[str, Any]) -> None:
    payload["useCases"].append(dict(payload["useCases"][0]))
    assert IntegrityCode.DUPLICATE_ID in codes_for(payload)


# --------------------------------------------------------------------------
# The four required reference checks
# --------------------------------------------------------------------------


def test_relationship_from_must_resolve_to_an_entity(payload: dict[str, Any]) -> None:
    payload["relationships"][0]["from"] = "no-such-entity"
    issues = issues_for(payload)
    assert IntegrityCode.UNKNOWN_ENTITY_REF in {i.code for i in issues}
    assert any(i.path == "relationships[0].from" for i in issues)
    assert any(i.offending_id == "no-such-entity" for i in issues)


def test_relationship_to_must_resolve_to_an_entity(payload: dict[str, Any]) -> None:
    payload["relationships"][0]["to"] = "no-such-entity"
    issues = issues_for(payload)
    assert IntegrityCode.UNKNOWN_ENTITY_REF in {i.code for i in issues}
    assert any(i.path == "relationships[0].to" for i in issues)


def test_use_case_actor_must_resolve_to_an_actor(payload: dict[str, Any]) -> None:
    payload["useCases"][0]["actors"] = ["no-such-actor"]
    issues = issues_for(payload)
    assert IntegrityCode.UNKNOWN_ACTOR_REF in {i.code for i in issues}
    assert any(i.path == "useCases[0].actors[0]" for i in issues)


def test_use_case_actor_may_not_point_at_an_entity(payload: dict[str, Any]) -> None:
    entity_only = next(
        entity["id"]
        for entity in payload["entities"]
        if entity["id"] not in {actor["id"] for actor in payload["actors"]}
    )
    payload["useCases"][0]["actors"] = [entity_only]
    assert IntegrityCode.UNKNOWN_ACTOR_REF in codes_for(payload)


def test_state_entity_ref_must_resolve_to_an_entity(payload: dict[str, Any]) -> None:
    payload["states"][0]["entityRef"] = "no-such-entity"
    issues = issues_for(payload)
    assert IntegrityCode.UNKNOWN_ENTITY_REF in {i.code for i in issues}
    assert any(i.path == "states[0].entityRef" for i in issues)


# --------------------------------------------------------------------------
# The additional unambiguous reference checks
# --------------------------------------------------------------------------


def test_node_deployed_component_must_resolve_to_a_component(payload: dict[str, Any]) -> None:
    payload["nodes"][0]["deployedComponents"] = ["no-such-component"]
    issues = issues_for(payload)
    assert IntegrityCode.UNKNOWN_COMPONENT_REF in {i.code for i in issues}
    assert any(i.path == "nodes[0].deployedComponents[0]" for i in issues)


def test_flow_participant_must_resolve_to_an_actor_or_an_entity(
    payload: dict[str, Any],
) -> None:
    payload["flows"][0]["participants"].append("no-such-participant")
    assert IntegrityCode.UNKNOWN_PARTICIPANT_REF in codes_for(payload)


def test_flow_step_endpoint_must_be_a_declared_participant(payload: dict[str, Any]) -> None:
    # A sequence diagram cannot draw a message to a lifeline that does not
    # exist, so this must fail at the gate rather than at render time.
    flow = payload["flows"][0]
    known_entity = next(
        entity["id"] for entity in payload["entities"] if entity["id"] not in flow["participants"]
    )
    flow["steps"][0]["to"] = known_entity
    issues = issues_for(payload)
    assert IntegrityCode.STEP_ENDPOINT_NOT_A_PARTICIPANT in {i.code for i in issues}
    assert any(i.path == "flows[0].steps[0].to" for i in issues)


def test_duplicate_flow_step_order_is_reported(payload: dict[str, Any]) -> None:
    # Two steps sharing an order make the render order dependent on input
    # ordering, which breaks determinism (FR-9).
    flow = payload["flows"][0]
    flow["steps"][1]["order"] = flow["steps"][0]["order"]
    assert IntegrityCode.DUPLICATE_STEP_ORDER in codes_for(payload)


def test_state_transition_must_resolve_to_a_known_state(payload: dict[str, Any]) -> None:
    payload["states"][0]["transitions"][0]["to"] = "no-such-state"
    issues = issues_for(payload)
    assert IntegrityCode.UNKNOWN_STATE_REF in {i.code for i in issues}
    assert any(i.path == "states[0].transitions[0].to" for i in issues)


def test_state_transition_may_not_cross_to_another_entitys_state(
    payload: dict[str, Any],
) -> None:
    origin = payload["states"][0]
    foreign = next(
        state for state in payload["states"] if state["entityRef"] != origin["entityRef"]
    )
    origin["transitions"][0]["to"] = foreign["id"]
    assert IntegrityCode.STATE_TRANSITION_CROSSES_ENTITY in codes_for(payload)


# --------------------------------------------------------------------------
# Error reporting quality
# --------------------------------------------------------------------------


def test_all_issues_are_reported_not_just_the_first(payload: dict[str, Any]) -> None:
    payload["relationships"][0]["from"] = "nope-one"
    payload["relationships"][1]["to"] = "nope-two"
    payload["useCases"][0]["actors"] = ["nope-three"]

    offending = {issue.offending_id for issue in issues_for(payload)}
    assert {"nope-one", "nope-two", "nope-three"} <= offending


def test_every_issue_carries_a_code_a_path_and_a_message(payload: dict[str, Any]) -> None:
    payload["relationships"][0]["from"] = "nope"
    for issue in issues_for(payload):
        assert issue.code in set(IntegrityCode)
        assert issue.path
        assert issue.message


def test_constructing_a_cpm_fails_closed_on_any_integrity_violation(
    payload: dict[str, Any],
) -> None:
    payload["states"][0]["entityRef"] = "no-such-entity"
    with pytest.raises(ValidationError) as excinfo:
        CPM.model_validate(payload)
    assert "states[0].entityRef" in str(excinfo.value)
