"""The Library Management System fixture.

Reused constantly: it is the input for AT-1 in the SRS, the seed for local
development, and the corpus for every downstream diagram-mapper test. If it
stops satisfying the AT-1 floor, those tests stop proving what they claim to.
"""

from typing import Any

from cpm.fixtures import (
    LIBRARY_MANAGEMENT_SYSTEM_PATH,
    library_management_system_payload,
    load_library_management_system,
)
from cpm.schema import CPM


def test_fixture_file_exists_on_disk() -> None:
    assert LIBRARY_MANAGEMENT_SYSTEM_PATH.is_file()


def test_fixture_loads_as_a_fully_valid_cpm() -> None:
    assert isinstance(load_library_management_system(), CPM)


def test_fixture_meets_the_at1_entity_and_relationship_floor() -> None:
    # SRS §10.1: a CPM containing >= 5 entities and >= 4 relationships.
    cpm = load_library_management_system()
    assert len(cpm.entities) >= 5
    assert len(cpm.relationships) >= 4


def test_fixture_populates_every_collection_the_eight_diagrams_need() -> None:
    # Class/ER need entities+relationships, Use Case needs actors+useCases,
    # Sequence needs flows, State needs states, Component needs components,
    # Deployment needs nodes. An empty collection means a diagram mapper would
    # have nothing to render.
    cpm = load_library_management_system()
    assert cpm.actors
    assert cpm.entities
    assert cpm.relationships
    assert cpm.use_cases
    assert cpm.flows
    assert cpm.states
    assert cpm.components
    assert cpm.nodes
    assert cpm.requirements


def test_fixture_exercises_the_actor_entity_overlap() -> None:
    cpm = load_library_management_system()
    actor_ids = {actor.id for actor in cpm.actors}
    entity_ids = {entity.id for entity in cpm.entities}
    assert actor_ids & entity_ids


def test_fixture_covers_multiple_relationship_types() -> None:
    cpm = load_library_management_system()
    assert len({relationship.type for relationship in cpm.relationships}) >= 3


def test_fixture_json_round_trips_byte_identically() -> None:
    payload: dict[str, Any] = library_management_system_payload()
    cpm = CPM.model_validate(payload)
    assert CPM.model_validate(cpm.model_dump(by_alias=True, mode="json")) == cpm


def test_fixture_payload_is_a_fresh_copy_each_call() -> None:
    # Callers mutate this to build negative test cases; handing out a shared
    # reference would let one test corrupt the next.
    first = library_management_system_payload()
    first["entities"].clear()
    assert library_management_system_payload()["entities"]
