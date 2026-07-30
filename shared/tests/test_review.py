"""The review gate: cascading edits, and the block on generating.

Two DoD properties are pinned here. A rename must reach every reference in one
pass — a rename that fixes the label and leaves the id behind produces a
diagram that still says the wrong thing. And an unconfirmed draft must be
incapable of being generated from, not merely discouraged from it.
"""

import inspect
from datetime import UTC, datetime

import pytest

from cpm.fixtures import library_management_system_payload
from cpm.schema import CPM, CPMDraft
from generation.run import execute_generation_run
from review import (
    NameCollision,
    NotConfirmable,
    UnknownElement,
    add_attribute,
    add_entity,
    add_relationship,
    confirm_draft,
    delete_actor,
    delete_entity,
    relink_relationship,
    rename_actor,
    rename_entity,
    review_state,
)

FIXED_TIME = datetime(2026, 7, 30, tzinfo=UTC)


@pytest.fixture
def draft() -> CPMDraft:
    return CPMDraft.model_validate(library_management_system_payload())


# --------------------------------------------------------------------------
# Rename cascades — DoD item 1
# --------------------------------------------------------------------------


def test_renaming_an_entity_rewrites_its_id(draft) -> None:
    outcome = rename_entity(draft, "book", "Publication")
    entity = next(e for e in outcome.draft.entities if e.name == "Publication")
    assert entity.id == "publication"


def test_renaming_an_entity_updates_every_relationship_end(draft) -> None:
    before = [r.id for r in draft.relationships if "book" in (r.from_, r.to)]
    assert before, "fixture must exercise this"

    outcome = rename_entity(draft, "book", "Publication")
    assert not any("book" in (r.from_, r.to) for r in outcome.draft.relationships)
    after = [r.id for r in outcome.draft.relationships if "publication" in (r.from_, r.to)]
    assert sorted(after) == sorted(before), "relationships repointed, not dropped"


def test_renaming_an_entity_updates_state_ownership(draft) -> None:
    assert any(s.entity_ref == "book" for s in draft.states)
    outcome = rename_entity(draft, "book", "Publication")
    assert not any(s.entity_ref == "book" for s in outcome.draft.states)
    assert any(s.entity_ref == "publication" for s in outcome.draft.states)


def test_renaming_an_entity_updates_flow_participants_and_steps(draft) -> None:
    outcome = rename_entity(draft, "book", "Publication")
    for flow in outcome.draft.flows:
        assert "book" not in flow.participants
        for step in flow.steps:
            assert step.from_ != "book" and step.to != "book"


def test_renaming_an_actor_updates_use_case_actor_lists(draft) -> None:
    assert any("librarian" in u.actors for u in draft.use_cases)
    outcome = rename_actor(draft, "librarian", "Library Staff")
    assert not any("librarian" in u.actors for u in outcome.draft.use_cases)
    assert any("library-staff" in u.actors for u in outcome.draft.use_cases)


def test_a_rename_leaves_the_model_internally_consistent(draft) -> None:
    # The whole point: after the cascade there are no dangling references.
    outcome = rename_entity(draft, "book", "Publication")
    assert review_state(outcome.draft).issues == []


def test_a_rename_reports_how_many_references_it_touched(draft) -> None:
    # Shown in the UI. A rename that silently fixed six references looks
    # identical to one that fixed none.
    outcome = rename_entity(draft, "book", "Publication")
    assert outcome.references_updated > 0


def test_changing_only_the_capitalisation_still_works(draft) -> None:
    outcome = rename_entity(draft, "book", "BOOK")
    assert any(e.name == "BOOK" for e in outcome.draft.entities)


# --------------------------------------------------------------------------
# Atomicity
# --------------------------------------------------------------------------


def test_a_refused_rename_leaves_the_draft_completely_untouched(draft) -> None:
    original = draft.model_dump_json(by_alias=True)

    with pytest.raises(NameCollision):
        rename_entity(draft, "book", "Member")  # "member" already exists

    assert draft.model_dump_json(by_alias=True) == original


def test_operations_never_mutate_the_draft_they_were_given(draft) -> None:
    original = draft.model_dump_json(by_alias=True)
    rename_entity(draft, "book", "Publication")
    delete_entity(draft, "fine")
    add_entity(draft, "Shelf")
    assert draft.model_dump_json(by_alias=True) == original


def test_renaming_onto_an_existing_name_is_refused_with_a_readable_message(draft) -> None:
    with pytest.raises(NameCollision) as excinfo:
        rename_entity(draft, "book", "Member")
    message = str(excinfo.value)
    assert "already called" in message
    assert "Member" in message


def test_renaming_something_that_does_not_exist_says_so(draft) -> None:
    with pytest.raises(UnknownElement):
        rename_entity(draft, "no-such-entity", "Whatever")


# --------------------------------------------------------------------------
# Deleting cascades too
# --------------------------------------------------------------------------


def test_deleting_an_entity_removes_the_relationships_that_used_it(draft) -> None:
    outcome = delete_entity(draft, "fine")
    assert not any(e.id == "fine" for e in outcome.draft.entities)
    assert not any("fine" in (r.from_, r.to) for r in outcome.draft.relationships)
    assert review_state(outcome.draft).issues == []


def test_deleting_an_entity_removes_its_states_and_their_transitions(draft) -> None:
    outcome = delete_entity(draft, "book")
    assert not any(s.entity_ref == "book" for s in outcome.draft.states)
    surviving = {s.id for s in outcome.draft.states}
    for state in outcome.draft.states:
        assert all(t.to in surviving for t in state.transitions)


def test_deleting_an_actor_removes_it_from_use_cases(draft) -> None:
    outcome = delete_actor(draft, "administrator")
    assert not any("administrator" in u.actors for u in outcome.draft.use_cases)
    assert review_state(outcome.draft).issues == []


# --------------------------------------------------------------------------
# Adding and re-linking
# --------------------------------------------------------------------------


def test_adding_an_entity_keeps_the_model_valid(draft) -> None:
    outcome = add_entity(draft, "Shelf")
    assert any(e.id == "shelf" and e.name == "Shelf" for e in outcome.draft.entities)
    assert review_state(outcome.draft).issues == []


def test_adding_a_duplicate_entity_is_refused(draft) -> None:
    with pytest.raises(NameCollision):
        add_entity(draft, "Book")


def test_adding_an_attribute_appears_on_the_entity(draft) -> None:
    outcome = add_attribute(draft, "book", "shelfCode", "string")
    book = next(e for e in outcome.draft.entities if e.id == "book")
    assert any(a.name == "shelfCode" for a in book.attributes)


def test_relinking_a_relationship_moves_its_endpoint(draft) -> None:
    outcome = relink_relationship(draft, "rel-loan-incurs-fine", to_id="reservation")
    relationship = next(r for r in outcome.draft.relationships if r.id == "rel-loan-incurs-fine")
    assert relationship.to == "reservation"
    assert review_state(outcome.draft).issues == []


def test_relinking_to_something_that_does_not_exist_is_refused(draft) -> None:
    with pytest.raises(UnknownElement):
        relink_relationship(draft, "rel-loan-incurs-fine", to_id="ghost")


def test_a_new_relationship_gets_a_unique_id(draft) -> None:
    first = add_relationship(draft, "book", "fine").draft
    second = add_relationship(first, "book", "fine").draft
    ids = [r.id for r in second.relationships]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------
# The confirmation gate — DoD item 2
# --------------------------------------------------------------------------


def test_a_clean_draft_can_be_confirmed(draft) -> None:
    cpm = confirm_draft(draft, project_name="Library", created_at=FIXED_TIME)
    assert isinstance(cpm, CPM)
    assert cpm.meta.project_name == "Library"


def test_a_draft_with_problems_cannot_be_confirmed(draft) -> None:
    data = draft.model_dump(by_alias=True)
    data["relationships"][0]["from"] = "ghost-entity"
    broken = CPMDraft.model_validate(data)

    assert review_state(broken).issues
    with pytest.raises(NotConfirmable):
        confirm_draft(broken, project_name="Library")


def test_an_empty_draft_cannot_be_confirmed(draft) -> None:
    empty = CPMDraft.model_validate({"meta": draft.meta.model_dump(by_alias=True)})
    with pytest.raises(NotConfirmable) as excinfo:
        confirm_draft(empty, project_name="Library")
    assert "nothing to generate" in str(excinfo.value)


def test_the_refusal_explains_what_to_fix_in_plain_language(draft) -> None:
    data = draft.model_dump(by_alias=True)
    data["relationships"][0]["from"] = "ghost-entity"

    with pytest.raises(NotConfirmable) as excinfo:
        confirm_draft(CPMDraft.model_validate(data), project_name="Library")

    message = str(excinfo.value)
    assert "points at a thing that is not in the list" in message
    assert "unknown_entity_ref" not in message, "developer jargon must not reach the user"


def test_generation_cannot_accept_an_unconfirmed_draft() -> None:
    # FR-6 enforced by the type system, not by a check somebody could skip:
    # the run takes a CPM, and confirm_draft is the only way to make one from
    # a draft. There is no path from an unreviewed model to a diagram.
    annotation = inspect.signature(execute_generation_run).parameters["cpm"].annotation
    assert annotation is CPM or annotation == "CPM"


def test_a_draft_is_not_a_cpm(draft) -> None:
    assert not isinstance(draft, CPM)


def test_confirming_produces_a_value_that_can_be_stored_immutably(draft) -> None:
    # FR-7: the confirmed model is serialised and written once; the API never
    # updates that row.
    first = confirm_draft(draft, project_name="Library", created_at=FIXED_TIME)
    second = confirm_draft(draft, project_name="Library", created_at=FIXED_TIME)
    assert first.model_dump_json(by_alias=True) == second.model_dump_json(by_alias=True)


# --------------------------------------------------------------------------
# The state the screen renders from
# --------------------------------------------------------------------------


def test_issues_are_addressed_to_the_user_not_the_developer(draft) -> None:
    data = draft.model_dump(by_alias=True)
    data["useCases"][0]["actors"] = ["nobody"]
    state = review_state(CPMDraft.model_validate(data))

    assert state.issues
    assert all(issue.explanation for issue in state.issues)
    assert not state.confirmable


def test_issues_can_be_located_against_the_field_that_caused_them(draft) -> None:
    data = draft.model_dump(by_alias=True)
    data["relationships"][0]["from"] = "ghost-entity"
    state = review_state(CPMDraft.model_validate(data))

    assert state.issues_for("relationships[0]")
    assert not state.issues_for("entities[0]")


def test_a_healthy_draft_reports_confirmable(draft) -> None:
    state = review_state(draft)
    assert state.confirmable
    assert state.entity_count == len(draft.entities)
