"""The AST layer: numbering, cross-references, and exporter independence.

These tests do not build an SRS. They exercise the document tree on its own,
because that is the claim being made — that there is a layer here which knows
nothing about DOCX or PDF and which both exporters can render from. A layer
that can only be tested through the assembler is not a layer.
"""

import ast as python_ast
from pathlib import Path

import pytest

from srs import ast as srs_ast
from srs.ast import (
    Document,
    DocumentMeta,
    Figure,
    FigureRef,
    ListOfFigures,
    ListOfTables,
    Section,
    SectionRef,
    Table,
    TableOfContents,
    TableRef,
    figures,
    para,
    tables,
    walk_sections,
)
from srs.numbering import UnresolvedReference, number, render_runs

META = DocumentMeta(project_name="Test System", version="1.0")


def figure(name: str) -> Figure:
    return Figure(
        figure_id=f"fig-{name}",
        caption=f"{name} diagram",
        image=b"<svg/>",
        mime="image/svg+xml",
        alt=name,
        diagram_type=name,
    )


def table(name: str) -> Table:
    return Table(table_id=f"tbl-{name}", caption=f"{name} table", columns=("A",), rows=(("1",),))


def document(*sections: Section, front: tuple = ()) -> Document:
    return Document(title="T", meta=META, front_matter=front, sections=sections)


# --------------------------------------------------------------------------
# Section numbering
# --------------------------------------------------------------------------


def test_sections_are_numbered_hierarchically() -> None:
    doc = number(
        document(
            Section("a", "Introduction", subsections=(Section("a1", "Purpose"),)),
            Section(
                "b",
                "Requirements",
                subsections=(
                    Section("b1", "Functional", subsections=(Section("b1a", "Borrowing"),)),
                    Section("b2", "Performance"),
                ),
            ),
        )
    )

    assert [(s.number, s.title) for s in walk_sections(doc)] == [
        ("1", "Introduction"),
        ("1.1", "Purpose"),
        ("2", "Requirements"),
        ("2.1", "Functional"),
        ("2.1.1", "Borrowing"),
        ("2.2", "Performance"),
    ]


def test_numbering_does_not_mutate_its_input() -> None:
    # Numbering twice must not produce "1.1.1.1", and an exporter handed the
    # tree must not be able to renumber the caller's copy.
    original = document(Section("a", "One", subsections=(Section("a1", "Two"),)))
    once = number(original)
    twice = number(once)

    assert original.sections[0].number is None
    assert [s.number for s in walk_sections(once)] == [s.number for s in walk_sections(twice)]


# --------------------------------------------------------------------------
# Figure and table numbering
# --------------------------------------------------------------------------


def test_figures_are_numbered_sequentially_in_reading_order() -> None:
    doc = number(
        document(
            Section("a", "A", blocks=(figure("use_case"),)),
            Section(
                "b",
                "B",
                blocks=(figure("class"),),
                subsections=(Section("b1", "B1", blocks=(figure("state"),)),),
            ),
        )
    )

    assert [(f.number, f.diagram_type) for f in figures(doc)] == [
        (1, "use_case"),
        (2, "class"),
        (3, "state"),
    ]
    assert [f.label for f in figures(doc)] == ["Figure 1", "Figure 2", "Figure 3"]


def test_figure_numbers_are_gapless_across_the_whole_document() -> None:
    doc = number(
        document(*(Section(f"s{i}", f"S{i}", blocks=(figure(f"d{i}"),)) for i in range(6)))
    )
    assert [f.number for f in figures(doc)] == [1, 2, 3, 4, 5, 6]


def test_tables_are_numbered_independently_of_figures() -> None:
    doc = number(
        document(
            Section("a", "A", blocks=(figure("class"), table("x"), figure("state"), table("y")))
        )
    )
    assert [f.number for f in figures(doc)] == [1, 2]
    assert [t.number for t in tables(doc)] == [1, 2]


# --------------------------------------------------------------------------
# Cross-references
# --------------------------------------------------------------------------


def test_a_reference_renders_the_number_the_figure_was_actually_given() -> None:
    # The property that matters: the sentence and the caption cannot disagree,
    # because neither one holds the number.
    doc = number(
        document(
            Section("a", "A", blocks=(figure("use_case"),)),
            Section("b", "B", blocks=(para("See ", FigureRef("fig-class"), "."), figure("class"))),
        )
    )

    body = doc.sections[1].blocks[0]
    assert render_runs(body.runs) == "See Figure 2."
    assert figures(doc)[1].label == "Figure 2"


def test_moving_a_figure_moves_the_reference_with_it() -> None:
    reference = para("See ", FigureRef("fig-class"), ".")
    first = number(
        document(
            Section("a", "A", blocks=(figure("class"), reference)),
            Section("b", "B", blocks=(figure("state"),)),
        )
    )
    second = number(
        document(
            Section("a", "A", blocks=(figure("state"), reference)),
            Section("b", "B", blocks=(figure("class"),)),
        )
    )

    assert render_runs(first.sections[0].blocks[1].runs) == "See Figure 1."
    assert render_runs(second.sections[0].blocks[1].runs) == "See Figure 2."


def test_table_and_section_references_resolve_too() -> None:
    doc = number(
        document(
            Section(
                "a", "A", blocks=(table("x"), para(TableRef("tbl-x"), " and ", SectionRef("b")))
            ),
            Section("b", "B"),
        )
    )
    assert render_runs(doc.sections[0].blocks[1].runs) == "Table 1 and Section 2"


def test_a_dangling_reference_is_loud() -> None:
    with pytest.raises(UnresolvedReference) as excinfo:
        number(document(Section("a", "A", blocks=(para(FigureRef("fig-nope")),))))
    assert "fig-nope" in str(excinfo.value)


def test_rendering_an_unnumbered_reference_refuses_rather_than_guessing() -> None:
    with pytest.raises(UnresolvedReference):
        render_runs((FigureRef("fig-class"),))


# --------------------------------------------------------------------------
# The index tables
# --------------------------------------------------------------------------


def test_the_index_tables_are_derived_from_the_numbered_tree() -> None:
    doc = number(
        document(
            Section("a", "Introduction", blocks=(table("glossary"),)),
            Section("b", "Body", blocks=(figure("class"),)),
            front=(TableOfContents(), ListOfFigures(), ListOfTables()),
        )
    )
    contents, list_of_figures, list_of_tables = doc.front_matter

    assert [(e.number, e.title) for e in contents.entries] == [
        ("1", "Introduction"),
        ("2", "Body"),
    ]
    assert [(e.number, e.title) for e in list_of_figures.entries] == [("1", "class diagram")]
    assert [(e.number, e.title) for e in list_of_tables.entries] == [("1", "glossary table")]


def test_every_index_entry_points_at_something_the_document_contains() -> None:
    doc = number(
        document(
            Section("a", "A", subsections=(Section("a1", "A1", blocks=(figure("class"),)),)),
            front=(TableOfContents(), ListOfFigures()),
        )
    )
    contents, list_of_figures = doc.front_matter

    section_ids = {s.section_id for s in walk_sections(doc)}
    figure_ids = {f.figure_id for f in figures(doc)}
    assert {e.target_id for e in contents.entries} <= section_ids
    assert {e.target_id for e in list_of_figures.entries} <= figure_ids
    # …and the numbers in the index are the numbers on the things themselves.
    assert {e.number for e in contents.entries} == {s.number for s in walk_sections(doc)}
    assert {int(e.number) for e in list_of_figures.entries} == {f.number for f in figures(doc)}


def test_the_contents_depth_matches_the_section_depth() -> None:
    doc = number(
        document(
            Section("a", "A", subsections=(Section("a1", "A1", subsections=(Section("x", "X"),)),)),
            front=(TableOfContents(),),
        )
    )
    assert [e.depth for e in doc.front_matter[0].entries] == [1, 2, 3]


# --------------------------------------------------------------------------
# The layering claim
# --------------------------------------------------------------------------


def test_the_ast_imports_nothing_that_renders() -> None:
    # If the AST ever imports python-docx or reportlab, the layer has stopped
    # being a layer and one export format has started dictating the other.
    forbidden = {"docx", "reportlab", "weasyprint", "pdfkit", "fpdf", "odf", "jinja2"}
    for module in ("ast", "numbering", "placeholders", "ieee830"):
        path = Path(srs_ast.__file__).with_name(f"{module}.py")
        tree = python_ast.parse(path.read_text(encoding="utf-8"))
        for node in python_ast.walk(tree):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, python_ast.Import)
                else [node.module or ""]
                if isinstance(node, python_ast.ImportFrom)
                else []
            )
            assert not {name.split(".")[0] for name in names} & forbidden, (
                f"{module} imports a renderer"
            )


def test_two_independent_exporters_agree_on_every_number() -> None:
    """The point of the layer, stated as a test.

    Two renderers, written independently over the same tree, produce the same
    numbering — because neither of them decides it. This is what would be lost
    if one format were generated from the other's output.
    """
    doc = number(
        document(
            Section("a", "Intro", blocks=(para("See ", FigureRef("fig-class"), "."),)),
            Section("b", "Body", blocks=(figure("class"), table("t"))),
            front=(TableOfContents(),),
        )
    )

    def as_plain_text(document: Document) -> list[str]:
        out = []
        for section in walk_sections(document):
            out.append(f"{section.number} {section.title}")
            for block in section.blocks:
                if hasattr(block, "runs"):
                    out.append(render_runs(block.runs))
                elif isinstance(block, Figure | Table):
                    out.append(f"{block.label}: {block.caption}")
        return out

    def as_markdown(document: Document) -> list[str]:
        out = []
        for section in walk_sections(document):
            depth = len((section.number or "").split("."))
            out.append(f"{'#' * depth} {section.number} {section.title}")
            for block in section.blocks:
                if hasattr(block, "runs"):
                    out.append(render_runs(block.runs))
                elif isinstance(block, Figure):
                    out.append(
                        f"![{block.alt}]({block.figure_id}) *{block.label}: {block.caption}*"
                    )
                elif isinstance(block, Table):
                    out.append(f"**{block.label}: {block.caption}**")
        return out

    plain, markdown = as_plain_text(doc), as_markdown(doc)

    assert "See Figure 1." in plain and "See Figure 1." in markdown
    assert any("Figure 1: class diagram" in line for line in plain)
    assert any("Figure 1: class diagram" in line for line in markdown)
    assert any("Table 1: t table" in line for line in plain)
    assert any("Table 1: t table" in line for line in markdown)
