"""Golden-file tests for the mappers, plus the properties goldens cannot check.

A golden file catches *change*. It cannot catch a mapper that was wrong on the
day it was written, because the golden was generated from that same mapper. So
every golden here is paired with assertions about what the source must contain
— arrow notation, key markers, and above all FR-10's byte-identical naming.
"""

from pathlib import Path

import pytest

from cpm.fixtures import load_library_management_system
from diagrams.registry import get_mapper, registry

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

EXTENSION = {"plantuml": "puml", "mermaid": "mmd"}


def golden_path(diagram_type: str) -> Path:
    mapper = get_mapper(diagram_type)
    return GOLDEN_DIR / f"{diagram_type}.{EXTENSION[str(mapper.engine)]}"


@pytest.fixture(scope="module")
def cpm():
    return load_library_management_system()


# --------------------------------------------------------------------------
# Golden files
# --------------------------------------------------------------------------


@pytest.mark.parametrize("diagram_type", sorted(registry()))
def test_source_matches_the_golden_file_byte_for_byte(diagram_type: str, cpm) -> None:
    path = golden_path(diagram_type)
    assert path.is_file(), f"missing golden {path.name}; regenerate with `make golden`"

    produced = get_mapper(diagram_type).to_source(cpm)
    expected = path.read_text(encoding="utf-8")
    assert produced == expected, (
        f"{diagram_type} source changed. If the change is intended, run "
        "`make golden` and review the diff."
    )


@pytest.mark.parametrize("diagram_type", sorted(registry()))
def test_the_same_cpm_produces_the_same_source_twice(diagram_type: str, cpm) -> None:
    mapper = get_mapper(diagram_type)
    assert mapper.to_source(cpm) == mapper.to_source(cpm)


@pytest.mark.parametrize("diagram_type", sorted(registry()))
def test_two_equal_cpms_produce_the_same_source(diagram_type: str) -> None:
    # FR-9 stated properly: the source is a function of the model's content,
    # not of the particular object that carried it.
    mapper = get_mapper(diagram_type)
    first = load_library_management_system()
    second = load_library_management_system()
    assert first == second
    assert mapper.to_source(first) == mapper.to_source(second)


# --------------------------------------------------------------------------
# FR-10: names are byte-identical to the CPM, everywhere
# --------------------------------------------------------------------------


@pytest.mark.parametrize("diagram_type", ["class", "entity_relationship"])
def test_every_entity_name_appears_verbatim(diagram_type: str, cpm) -> None:
    source = get_mapper(diagram_type).to_source(cpm)
    for entity in cpm.entities:
        assert entity.name in source, f"{entity.name!r} missing from {diagram_type}"


def test_every_actor_and_use_case_name_appears_verbatim(cpm) -> None:
    source = get_mapper("use_case").to_source(cpm)
    for actor in cpm.actors:
        assert actor.name in source
    for use_case in cpm.use_cases:
        assert use_case.name in source


def test_names_are_not_recased_for_the_er_diagram(cpm) -> None:
    # The obvious ER convention is SHOUTING entity names. It would break FR-10,
    # so it is not done — and this pins that.
    source = get_mapper("entity_relationship").to_source(cpm)
    assert "Book" in source
    assert "BOOK" not in source


# --------------------------------------------------------------------------
# Class diagram specifics
# --------------------------------------------------------------------------


def test_class_diagram_uses_correct_uml_arrows(cpm) -> None:
    source = get_mapper("class").to_source(cpm)
    assert "*--" in source, "composition"
    assert "o--" in source, "aggregation"
    assert "--|>" in source, "inheritance"
    assert "..>" in source, "dependency"


def test_class_diagram_marks_key_attributes(cpm) -> None:
    source = get_mapper("class").to_source(cpm)
    assert "isbn : string [key]" in source


def test_class_diagram_renders_methods_with_parameters(cpm) -> None:
    source = get_mapper("class").to_source(cpm)
    assert "+ reserve(memberId: string) : Reservation" in source


def test_class_diagram_aliases_avoid_hyphens(cpm) -> None:
    # PlantUML parses a hyphen as part of an arrow, so ids become underscored
    # aliases. The display name is unaffected, which is why FR-10 still holds.
    source = get_mapper("class").to_source(cpm)
    assert " as state_book_available" not in source  # not an entity
    for entity in cpm.entities:
        assert f"as {entity.id.replace('-', '_')}" in source


# --------------------------------------------------------------------------
# ER diagram specifics
# --------------------------------------------------------------------------


def test_er_diagram_marks_primary_keys(cpm) -> None:
    source = get_mapper("entity_relationship").to_source(cpm)
    assert "string isbn PK" in source


def test_er_diagram_maps_cardinality_to_crows_feet(cpm) -> None:
    source = get_mapper("entity_relationship").to_source(cpm)
    assert "||--|{" in source or "||..|{" in source, "1..* should be one-or-more"
    assert "||--o|" in source or "||..o|" in source, "0..1 should be zero-or-one"


def test_er_entity_names_with_spaces_are_quoted() -> None:
    from cpm.schema import CPM

    cpm = CPM.model_validate(
        {
            "meta": {"projectName": "P", "createdAt": "2026-07-30T00:00:00Z"},
            "entities": [
                {"id": "meal-attendance", "name": "Meal Attendance"},
                {"id": "bill", "name": "Bill"},
            ],
            "relationships": [
                {"id": "r1", "from": "meal-attendance", "to": "bill", "type": "association"}
            ],
        }
    )
    source = get_mapper("entity_relationship").to_source(cpm)
    assert '"Meal Attendance" {' in source
    assert "\n    Bill {" in source, "a safe name needs no quotes"


# --------------------------------------------------------------------------
# Use case diagram specifics
# --------------------------------------------------------------------------


def test_use_case_diagram_puts_the_project_name_on_the_boundary(cpm) -> None:
    source = get_mapper("use_case").to_source(cpm)
    assert f'rectangle "{cpm.meta.project_name}" {{' in source


def test_use_case_diagram_links_each_actor_to_its_use_cases(cpm) -> None:
    source = get_mapper("use_case").to_source(cpm)
    for use_case in cpm.use_cases:
        for actor_id in use_case.actors:
            assert f"{actor_id.replace('-', '_')} --> {use_case.id.replace('-', '_')}" in source


# --------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------


def test_plantuml_sources_are_wrapped_correctly(cpm) -> None:
    for diagram_type in ("class", "use_case"):
        source = get_mapper(diagram_type).to_source(cpm)
        assert source.startswith("@startuml")
        assert source.rstrip().endswith("@enduml")


def test_the_mermaid_source_declares_an_er_diagram(cpm) -> None:
    assert get_mapper("entity_relationship").to_source(cpm).startswith("erDiagram")


@pytest.mark.parametrize("diagram_type", sorted(registry()))
def test_source_ends_with_exactly_one_newline(diagram_type: str, cpm) -> None:
    source = get_mapper(diagram_type).to_source(cpm)
    assert source.endswith("\n")
    assert not source.endswith("\n\n")
