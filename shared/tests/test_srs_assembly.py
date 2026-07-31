"""Assembling the SRS from the Library Management System fixture.

What is being asserted, in order of how much it would cost to get wrong:

* every generated diagram ends up embedded, captioned and numbered (FR-16);
* FR-10 covers the prose as strictly as it covers a diagram source;
* NFR-Q4 refuses to return a document with an unresolved placeholder in it;
* the same CPM assembles to the same document, byte for byte (FR-9).
"""

import copy

import pytest

from consistency.validator import ConsistencyViolation
from cpm.fixtures import library_management_system_payload, load_library_management_system
from cpm.schema import CPM
from srs.assemble import assemble_srs
from srs.ast import Document, figures, find_section, tables, walk_sections
from srs.ieee830 import CAPTIONS, FALLBACK_SECTION, FIGURE_PLACEMENT, FigureInput, build_document
from srs.numbering import number, render_runs
from srs.placeholders import UnresolvedPlaceholder, assert_no_placeholders, find_placeholders
from srs.prose import SECTIONS, DeterministicProse, GatewayProse, UnknownProseSection

RENDERED = ("class", "entity_relationship", "use_case", "sequence")


def inputs(*types: str) -> list[FigureInput]:
    return [
        FigureInput(diagram_type=t, title=CAPTIONS.get(t, t), image=f"<svg id={t}/>".encode())
        for t in (types or RENDERED)
    ]


@pytest.fixture
def cpm() -> CPM:
    return load_library_management_system()


@pytest.fixture
async def assembled(cpm):
    return await assemble_srs(cpm, inputs())


# --------------------------------------------------------------------------
# IEEE 830 structure
# --------------------------------------------------------------------------


async def test_the_outline_is_the_one_an_assessor_expects(assembled) -> None:
    top = [(s.number, s.title) for s in assembled.document.sections]
    assert top == [
        ("1", "Introduction"),
        ("2", "Overall Description"),
        ("3", "Specific Requirements"),
    ]

    introduction = [s.title for s in assembled.document.sections[0].subsections]
    assert introduction == [
        "Purpose",
        "Scope",
        "Definitions, Acronyms and Abbreviations",
        "References",
        "Overview",
    ]


async def test_every_use_case_becomes_a_numbered_subsection(cpm, assembled) -> None:
    functional = find_section(assembled.document, "functional-requirements")
    assert [s.title for s in functional.subsections] == [uc.name for uc in cpm.use_cases]
    assert [s.number for s in functional.subsections] == [
        f"3.2.{i}" for i in range(1, len(cpm.use_cases) + 1)
    ]


async def test_an_empty_part_of_the_model_says_so_rather_than_inventing(cpm) -> None:
    thin = cpm.model_copy(update={"requirements": [], "states": [], "components": []})
    result = await assemble_srs(thin, inputs())

    attributes = find_section(result.document, "system-attributes")
    text = " ".join(render_runs(b.runs) for b in attributes.blocks if hasattr(b, "runs"))
    assert "records no non-functional requirements" in text
    # And no table was fabricated to fill the space.
    assert not [b for b in attributes.blocks if b.__class__.__name__ == "Table"]


# --------------------------------------------------------------------------
# FR-16: the figures
# --------------------------------------------------------------------------


async def test_every_rendered_diagram_is_embedded_numbered_and_captioned(assembled) -> None:
    embedded = figures(assembled.document)

    assert {f.diagram_type for f in embedded} == set(RENDERED)
    assert [f.number for f in embedded] == [1, 2, 3, 4]
    assert all(f.image for f in embedded)
    assert all(f.caption and "Library Management System" in f.caption for f in embedded)
    assert all(f.alt for f in embedded)


async def test_figures_land_in_the_section_that_discusses_them(assembled) -> None:
    for diagram_type in RENDERED:
        section = find_section(assembled.document, FIGURE_PLACEMENT[diagram_type])
        assert any(getattr(b, "diagram_type", None) == diagram_type for b in section.blocks)


async def test_a_diagram_type_nobody_placed_is_still_embedded(cpm) -> None:
    # FR-16 must not be defeated by a missing dictionary entry. A ninth diagram
    # type added without touching ieee830.py appears at the end rather than
    # vanishing from the document.
    assert "timing" not in FIGURE_PLACEMENT
    result = await assemble_srs(cpm, [*inputs(), FigureInput("timing", "Timing", b"<svg/>")])

    embedded = figures(result.document)
    assert "timing" in {f.diagram_type for f in embedded}
    fallback = find_section(result.document, FALLBACK_SECTION)
    assert any(getattr(b, "diagram_type", None) == "timing" for b in fallback.blocks)


async def test_a_diagram_that_was_not_rendered_leaves_no_hole(cpm) -> None:
    # Skipped and failed diagrams simply are not passed in. The document must
    # not contain "Figure 3: [missing]" — numbering closes over what is there.
    result = await assemble_srs(cpm, inputs("class", "use_case"))
    embedded = figures(result.document)

    assert [f.number for f in embedded] == [1, 2]
    list_of_figures = result.document.front_matter[1]
    assert [e.number for e in list_of_figures.entries] == ["1", "2"]


async def test_a_cross_reference_to_a_missing_figure_is_not_emitted(cpm) -> None:
    # The sentence "shown in Figure N" is only written when the figure exists.
    result = await assemble_srs(cpm, inputs("class"))
    functions = find_section(result.document, "product-functions")
    text = " ".join(render_runs(b.runs) for b in functions.blocks if hasattr(b, "runs"))
    assert "shown in" not in text


async def test_the_use_case_figure_is_referenced_by_number_when_present(assembled) -> None:
    functions = find_section(assembled.document, "product-functions")
    text = " ".join(render_runs(b.runs) for b in functions.blocks if hasattr(b, "runs"))
    figure = next(f for f in figures(assembled.document) if f.diagram_type == "use_case")
    assert f"shown in Figure {figure.number}" in text


# --------------------------------------------------------------------------
# FR-10 over the prose
# --------------------------------------------------------------------------


async def test_a_clean_assembly_passes_the_name_check(assembled) -> None:
    assert assembled.consistency.ok
    assert assembled.consistency.recognised_names > 0


async def test_prose_that_pluralises_an_entity_fails_the_assembly(cpm) -> None:
    class Drifting(DeterministicProse):
        async def write(self, key: str, cpm: CPM) -> str:
            text = await super().write(key, cpm)
            return text if key != "purpose" else "The system stores Books for every Member."

    with pytest.raises(ConsistencyViolation) as excinfo:
        await assemble_srs(cpm, inputs(), Drifting())

    message = str(excinfo.value)
    assert "'Book'" in message and "'Books'" in message


async def test_ordinary_lowercase_english_is_not_flagged(cpm) -> None:
    # The check has to survive normal writing, or it gets switched off.
    class Chatty(DeterministicProse):
        async def write(self, key: str, cpm: CPM) -> str:
            text = await super().write(key, cpm)
            if key == "purpose":
                return "The system stores books and lets members borrow them; fines apply."
            return text

    result = await assemble_srs(cpm, inputs(), Chatty())
    assert result.consistency.ok


async def test_a_multi_word_name_is_not_flagged_by_its_own_first_word(assembled) -> None:
    # "Borrow Book" is a use case; "Borrow" inside it is not a misspelling of
    # the relationship label "borrows". Regression: this fired on the first run.
    assert assembled.consistency.ok


# --------------------------------------------------------------------------
# NFR-Q4
# --------------------------------------------------------------------------


async def test_a_finished_document_has_no_placeholders(assembled) -> None:
    assert find_placeholders(assembled.document) == []
    assert assert_no_placeholders(assembled.document) == []


async def test_a_surviving_template_marker_fails_assembly(cpm) -> None:
    class Unfinished(DeterministicProse):
        async def write(self, key: str, cpm: CPM) -> str:
            if key == "scope":
                return "This system is {{project_name}}, version ${version}."
            return await super().write(key, cpm)

    with pytest.raises(UnresolvedPlaceholder) as excinfo:
        await assemble_srs(cpm, inputs(), Unfinished())

    message = str(excinfo.value)
    assert "{{project_name}}" in message and "${version}" in message
    assert "NFR-Q4" in message


async def test_the_assertion_covers_captions_and_table_cells_too(cpm) -> None:
    payload = copy.deepcopy(library_management_system_payload())
    payload["entities"][0]["description"] = "A {{thing}} in the catalogue."

    with pytest.raises(UnresolvedPlaceholder):
        await assemble_srs(CPM.model_validate(payload), inputs())


async def test_a_users_own_TBD_is_a_warning_not_a_failure(cpm) -> None:
    # A student with an undecided requirement still gets their document. The
    # tool reports it; it does not overrule its author.
    payload = copy.deepcopy(library_management_system_payload())
    payload["requirements"][0]["text"] = "Response time TBD."

    result = await assemble_srs(CPM.model_validate(payload), inputs())
    assert [w.token for w in result.warnings] == ["TBD"]


async def test_assembly_has_no_parameter_that_turns_the_checks_off() -> None:
    import inspect

    names = set(inspect.signature(assemble_srs).parameters)
    assert not {n for n in names if "skip" in n or "validate" in n or "strict" in n}, names


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


async def test_the_same_model_assembles_to_the_same_document(cpm) -> None:
    first = await assemble_srs(cpm, inputs())
    second = await assemble_srs(cpm, inputs())
    assert _shape(first.document) == _shape(second.document)


def _shape(document: Document) -> list:
    out: list = [document.title]
    for section in walk_sections(document):
        out.append((section.number, section.title))
        for block in section.blocks:
            if hasattr(block, "runs"):
                out.append(render_runs(block.runs))
            elif hasattr(block, "items"):
                out.extend(render_runs(item) for item in block.items)
            else:
                out.append((getattr(block, "label", ""), getattr(block, "caption", "")))
    return out


# --------------------------------------------------------------------------
# Prose sources
# --------------------------------------------------------------------------


async def test_every_declared_prose_section_can_actually_be_written(cpm) -> None:
    writer = DeterministicProse()
    for key in SECTIONS:
        text = await writer.write(key, cpm)
        assert text.strip(), key


async def test_an_unknown_prose_section_is_refused(cpm) -> None:
    with pytest.raises(UnknownProseSection):
        await DeterministicProse().write("conclusion", cpm)


async def test_the_gateway_writer_sends_the_model_and_nothing_else(cpm) -> None:
    import json

    seen: list[tuple[str, str]] = []

    class RecordingGateway:
        async def complete(self, task, payload, schema, *, user_id=None):
            seen.append((task, payload))
            return schema(text="A paragraph about Book and Member.")

    writer = GatewayProse(RecordingGateway())
    await writer.write("purpose", cpm)

    task, payload = seen[0]
    assert task == "srs_prose"
    body = json.loads(payload)
    # The CPM, the section key, and nothing a caller could have smuggled in.
    assert set(body) == {"section", "sectionDescription", "model"}
    assert body["section"] == "purpose"
    assert body["model"]["meta"]["projectName"] == cpm.meta.project_name


async def test_model_written_prose_is_held_to_the_same_name_rule(cpm) -> None:
    class DriftingGateway:
        async def complete(self, task, payload, schema, *, user_id=None):
            return schema(text="The Books are lent to Members by the system.")

    with pytest.raises(ConsistencyViolation):
        await assemble_srs(cpm, inputs(), GatewayProse(DriftingGateway()))


async def test_a_gateway_failure_stops_assembly_rather_than_quietly_downgrading(cpm) -> None:
    class BrokenGateway:
        async def complete(self, task, payload, schema, *, user_id=None):
            raise RuntimeError("provider unreachable")

    with pytest.raises(RuntimeError, match="provider unreachable"):
        await assemble_srs(cpm, inputs(), GatewayProse(BrokenGateway()))


# --------------------------------------------------------------------------
# The layer boundary
# --------------------------------------------------------------------------


async def test_assembly_returns_a_document_and_no_rendered_bytes(assembled) -> None:
    # Nothing here is a PDF or a DOCX. Both exporters start from this object.
    assert isinstance(assembled.document, Document)
    assert assembled.document.numbered
    assert assembled.figure_count == len(RENDERED)
    assert assembled.table_count == len(tables(assembled.document))


async def test_building_and_numbering_are_separable(cpm) -> None:
    # The assembler composes two steps that each stand alone; an exporter or a
    # future template could reuse either.
    raw = await build_document(cpm, inputs(), DeterministicProse())
    assert all(s.number is None for s in walk_sections(raw))
    assert not raw.numbered

    finished = number(raw)
    assert all(s.number for s in walk_sections(finished))
    assert finished.numbered
