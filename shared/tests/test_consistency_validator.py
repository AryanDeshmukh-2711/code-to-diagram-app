"""FR-10 validation, proved by breaking it.

A validator that has never failed in a test is not a validator, so most of this
file corrupts real mapper output in the specific ways drift actually happens —
a plural, a re-casing, a stray space — and asserts each one is caught and
reported precisely.
"""

from dataclasses import dataclass

import pytest

from consistency.names import extract_mermaid, extract_names, extract_plantuml
from consistency.validator import (
    ConsistencyViolation,
    cpm_display_names,
    validate_consistency,
)
from cpm.fixtures import load_library_management_system
from diagrams.registry import get_mapper


@dataclass(frozen=True)
class FakeDiagram:
    diagram_type: str
    engine: str
    source: str
    ok: bool = True


@pytest.fixture(scope="module")
def cpm():
    return load_library_management_system()


def real_diagrams(cpm) -> list[FakeDiagram]:
    return [
        FakeDiagram(
            diagram_type=t, engine=str(get_mapper(t).engine), source=get_mapper(t).to_source(cpm)
        )
        for t in ("class", "entity_relationship", "use_case")
    ]


def corrupted(cpm, diagram_type: str, before: str, after: str) -> list[FakeDiagram]:
    """Real output from a real mapper, with one name damaged."""
    diagrams = []
    for diagram in real_diagrams(cpm):
        source = (
            diagram.source.replace(before, after)
            if diagram.diagram_type == diagram_type
            else diagram.source
        )
        diagrams.append(FakeDiagram(diagram.diagram_type, diagram.engine, source))
    return diagrams


# --------------------------------------------------------------------------
# The honest baseline
# --------------------------------------------------------------------------


def test_the_real_diagram_set_passes(cpm) -> None:
    report = validate_consistency(cpm, real_diagrams(cpm))
    assert report.ok, report.render()
    assert report.checked_diagrams == 3


def test_the_pass_is_not_vacuous(cpm) -> None:
    # A validator that recognises nothing passes everything.
    report = validate_consistency(cpm, real_diagrams(cpm))
    assert report.recognised_names > 20


def test_an_extractor_that_finds_nothing_is_itself_a_violation(cpm) -> None:
    empty = [FakeDiagram("class", "plantuml", "@startuml\nskinparam shadowing false\n@enduml\n")]
    report = validate_consistency(cpm, empty)
    assert not report.ok
    assert "extractor is broken" in report.render()


# --------------------------------------------------------------------------
# Corrupted mapper output — the point of the whole file
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("diagram_type", "before", "after", "expected", "found"),
    [
        ("class", '"Book"', '"Books"', "Book", "Books"),
        ("class", '"Book"', '"BOOK"', "Book", "BOOK"),
        ("class", '"Member"', '"member"', "Member", "member"),
        ("class", '"Loan"', '"Loan "', "Loan", "Loan "),
        ("class", '"Reservation"', '"Reservations"', "Reservation", "Reservations"),
        ("use_case", '"Librarian"', '"Librarians"', "Librarian", "Librarians"),
        ("use_case", '"Borrow Book"', '"Borrow Books"', "Borrow Book", "Borrow Books"),
        ("entity_relationship", "Book {", "Books {", "Book", "Books"),
        ("entity_relationship", "Fine {", "FINE {", "Fine", "FINE"),
    ],
)
def test_a_corrupted_name_is_caught(cpm, diagram_type, before, after, expected, found) -> None:
    report = validate_consistency(cpm, corrupted(cpm, diagram_type, before, after))

    assert not report.ok, f"{found!r} should not have passed as {expected!r}"
    violation = next(v for v in report.violations if v.found == found)
    assert violation.expected == expected
    assert violation.diagram_type == diagram_type
    assert violation.line > 0


def test_a_drifted_relationship_label_is_caught(cpm) -> None:
    damaged = corrupted(cpm, "class", ": borrows", ": Borrows")
    report = validate_consistency(cpm, damaged)
    assert not report.ok
    assert any(v.found == "Borrows" and v.expected == "borrows" for v in report.violations)


def test_a_substring_check_would_have_missed_this(cpm) -> None:
    # The trap this validator exists to avoid: "Book" IS a substring of
    # "Books", so a naive `name in source` passes the corrupted output.
    damaged = corrupted(cpm, "class", '"Book"', '"Books"')
    class_source = next(d.source for d in damaged if d.diagram_type == "class")

    assert "Book" in class_source, "a substring check sees nothing wrong here"
    assert not validate_consistency(cpm, damaged).ok, "the validator must still catch it"


def test_every_corruption_in_a_run_is_reported_not_just_the_first(cpm) -> None:
    # A user fixing one name at a time across four rounds is a user who gives up.
    damaged = []
    for diagram in real_diagrams(cpm):
        source = diagram.source.replace('"Book"', '"Books"').replace('"Member"', '"Members"')
        damaged.append(FakeDiagram(diagram.diagram_type, diagram.engine, source))

    report = validate_consistency(cpm, damaged)
    assert {v.found for v in report.violations} >= {"Books", "Members"}


def test_the_report_names_diagram_expected_and_found(cpm) -> None:
    report = validate_consistency(cpm, corrupted(cpm, "class", '"Book"', '"Books"'))
    rendered = report.render()

    assert "FAILED" in rendered
    assert "class" in rendered
    assert "'Book'" in rendered
    assert "'Books'" in rendered


def test_the_exception_carries_the_report(cpm) -> None:
    report = validate_consistency(cpm, corrupted(cpm, "class", '"Book"', '"Books"'))
    error = ConsistencyViolation(report)
    assert error.report is report
    assert "Books" in str(error)


# --------------------------------------------------------------------------
# Things that must NOT be flagged
# --------------------------------------------------------------------------


def test_cardinalities_and_keywords_are_not_mistaken_for_names(cpm) -> None:
    report = validate_consistency(cpm, real_diagrams(cpm))
    assert report.ok, report.render()


def test_attribute_types_are_not_compared_against_entity_names() -> None:
    # An attribute typed `string` must not be reported as drift from an entity
    # named `String`. False alarms are how a validator gets disabled.
    from cpm.schema import CPM

    cpm = CPM.model_validate(
        {
            "meta": {"projectName": "P", "createdAt": "2026-07-30T00:00:00Z"},
            "entities": [
                {
                    "id": "string",
                    "name": "String",
                    "attributes": [{"name": "value", "type": "string"}],
                },
                {"id": "other", "name": "Other"},
            ],
            "relationships": [{"id": "r1", "from": "string", "to": "other", "type": "association"}],
        }
    )
    diagrams = [
        FakeDiagram("class", "plantuml", get_mapper("class").to_source(cpm)),
        FakeDiagram(
            "entity_relationship", "mermaid", get_mapper("entity_relationship").to_source(cpm)
        ),
    ]
    assert validate_consistency(cpm, diagrams).ok


def test_a_failed_diagram_source_is_still_validated(cpm) -> None:
    # A source that was generated can still be handed to a user for diagnosis,
    # so it is held to the same standard.
    damaged = corrupted(cpm, "class", '"Book"', '"Books"')
    marked = [FakeDiagram(d.diagram_type, d.engine, d.source, ok=False) for d in damaged]
    assert not validate_consistency(cpm, marked).ok


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def test_plantuml_extraction_skips_class_members() -> None:
    source = 'class "Book" as book {\n  + isbn : string [key]\n}\n'
    assert [name.text for name in extract_plantuml(source)] == ["Book"]


def test_plantuml_extraction_picks_up_relationship_labels() -> None:
    found = [n.text for n in extract_plantuml('a --> "1..*" b : borrows\n')]
    assert "borrows" in found


def test_mermaid_extraction_skips_attribute_lines() -> None:
    source = "erDiagram\n    Book {\n        string isbn PK\n    }\n"
    assert [name.text for name in extract_mermaid(source)] == ["Book"]


def test_mermaid_extraction_reads_both_ends_and_the_label() -> None:
    found = [n.text for n in extract_mermaid('erDiagram\n    Member ||--o{ Loan : "borrows"\n')]
    assert found == ["Member", "Loan", "borrows"]


def test_mermaid_extraction_handles_quoted_entity_names() -> None:
    source = 'erDiagram\n    "Meal Attendance" {\n        date day\n    }\n'
    assert [name.text for name in extract_mermaid(source)] == ["Meal Attendance"]


def test_an_engine_with_no_extractor_is_a_loud_failure() -> None:
    # A diagram language the validator cannot read is a diagram FR-10 does not
    # cover. Skipping it silently would shrink the guarantee without saying so.
    from consistency.names import UnsupportedSourceLanguage

    with pytest.raises(UnsupportedSourceLanguage):
        extract_names("digraph {}", "graphviz")


def test_the_cpm_name_set_covers_every_displayed_kind(cpm) -> None:
    names = cpm_display_names(cpm)
    assert {e.name for e in cpm.entities} <= names
    assert {a.name for a in cpm.actors} <= names
    assert {u.name for u in cpm.use_cases} <= names
    assert {c.name for c in cpm.components} <= names
    assert {n.name for n in cpm.nodes} <= names
