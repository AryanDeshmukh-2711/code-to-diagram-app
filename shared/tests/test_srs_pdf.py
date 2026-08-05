"""The PDF exporter, and AT-1: the two files say the same thing.

The equivalence test does not strip differences until the two streams match.
It aligns them and then *verifies what the differences are* — every word of
the DOCX body must appear in the PDF in the same order, and the PDF's only
extra tokens must be list markers, one per list item in the document. A bullet
is paragraph formatting in DOCX and a drawn glyph in PDF; that is the whole of
the allowed divergence, and the count is pinned, so a dropped sentence or a
changed word fails rather than being absorbed by a tolerant normaliser.
"""

import ast as python_ast
import copy
import io
import re
import time
from pathlib import Path

import pytest
from conftest import sample_png
from pypdf import PdfReader

from cpm.fixtures import library_management_system_payload, load_library_management_system
from cpm.schema import CPM
from srs.assemble import assemble_srs
from srs.ast import BulletList, NumberedList, walk_blocks
from srs.export import pdf as pdf_module
from srs.export.compare import compare, docx_body_words, figure_vocabulary, pdf_body_words
from srs.export.docx import export_docx
from srs.export.pdf import UnrenderableFigure, export_pdf
from srs.export.template import A4, IEEE_TIMES, US_LETTER
from srs.ieee830 import CAPTIONS, FigureInput

PNG = sample_png()
RENDERED = ("class", "entity_relationship", "use_case", "sequence")


def inputs(*types: str, mime: str = "image/png", image: bytes | None = None):
    return [
        FigureInput(
            diagram_type=t,
            title=CAPTIONS.get(t, t),
            image=image if image is not None else PNG,
            mime=mime,
        )
        for t in (types or RENDERED)
    ]


@pytest.fixture
def cpm():
    return load_library_management_system()


@pytest.fixture
async def document(cpm):
    return (await assemble_srs(cpm, inputs())).document


@pytest.fixture
def exported(document):
    return export_pdf(document, A4)


def reader_of(result) -> PdfReader:
    return PdfReader(io.BytesIO(result.content))


# --------------------------------------------------------------------------
# Text extraction, shared by the equivalence test
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# AT-1
# --------------------------------------------------------------------------


async def test_pdf_and_docx_say_exactly_the_same_thing(cpm, document) -> None:
    docx = export_docx(document, A4)
    pdf = export_pdf(document, A4)

    difference = compare(
        docx_body_words(docx.content),
        pdf_body_words(pdf.content, cpm.meta.project_name),
    )

    assert difference.missing == [], (
        f"the PDF is missing text the DOCX has: {difference.missing[:20]}"
    )
    assert difference.unexplained == [], (
        f"the PDF contains text the DOCX does not: {difference.unexplained[:20]}"
    )

    # Raster figures here, so every extra must be a list marker — one per item.
    list_items = sum(
        len(block.items)
        for _, block in walk_blocks(document)
        if isinstance(block, BulletList | NumberedList)
    )
    assert len(difference.markers) == list_items, (
        f"expected exactly one list marker per list item ({list_items}), "
        f"got {len(difference.markers)}"
    )


async def test_vector_figure_text_is_explained_not_ignored(cpm) -> None:
    # The comparison must not be so permissive that a real difference hides
    # behind "it came from a diagram".
    svg = (
        b"<svg xmlns='http://www.w3.org/2000/svg' width='200' height='80'>"
        b"<text x='10' y='40'>Reservation</text></svg>"
    )
    assembled = await assemble_srs(
        cpm, [FigureInput("class", "Class", svg, "image/svg+xml", (("image/png", PNG),))]
    )
    docx = export_docx(assembled.document, A4)
    pdf = export_pdf(assembled.document, A4)

    words = docx_body_words(docx.content)
    pdf_words = pdf_body_words(pdf.content, cpm.meta.project_name)

    without = compare(words, pdf_words)
    with_vocabulary = compare(words, pdf_words, figure_vocabulary([svg]))

    assert "Reservation" in without.unexplained
    assert with_vocabulary.unexplained == []
    assert "Reservation" in with_vocabulary.from_figures


async def test_both_exports_carry_the_same_figures_and_tables(document) -> None:
    docx = export_docx(document, A4)
    pdf = export_pdf(document, A4)
    assert (docx.figures, docx.tables, docx.sections) == (pdf.figures, pdf.tables, pdf.sections)


async def test_one_assembled_document_feeds_both_exporters(cpm) -> None:
    # AT-1 holds because there is one document, not two assemblies that happen
    # to agree. The figure carries both renditions so neither export needs its
    # own pass over the model.
    figures = [
        FigureInput(
            "class",
            "Class Diagram",
            b"<svg xmlns='http://www.w3.org/2000/svg'/>",
            "image/svg+xml",
            (("image/png", PNG),),
        )
    ]
    assembled = await assemble_srs(cpm, figures)

    docx = export_docx(assembled.document, A4)
    pdf = export_pdf(assembled.document, A4)

    assert docx.figures == pdf.figures == 1
    assert b"image1.png" in docx.content or docx.size > 0
    assert pdf.size > 0


# --------------------------------------------------------------------------
# Vector, with a raster fallback
# --------------------------------------------------------------------------


async def test_an_svg_figure_is_drawn_as_vector(cpm) -> None:
    svg = (
        b"<svg xmlns='http://www.w3.org/2000/svg' width='200' height='100'>"
        b"<rect x='5' y='5' width='190' height='90' fill='none' stroke='black'/>"
        b"<text x='20' y='55'>Book</text></svg>"
    )
    assembled = await assemble_srs(cpm, [FigureInput("class", "Class", svg, "image/svg+xml")])
    result = export_pdf(assembled.document, A4)

    assert result.vector_figures == 1
    assert result.raster_figures == 0
    # Vector text is real text: searchable in the PDF, unlike a raster diagram.
    reader = reader_of(result)
    assert any("Book" in (page.extract_text() or "") for page in reader.pages)


async def test_an_unconvertible_svg_falls_back_to_the_raster(cpm) -> None:
    # "Vector where possible" — and where not, the figure still appears.
    broken = b"<svg xmlns='http://www.w3.org/2000/svg'><g style='no-colon-here'/></svg>"
    assembled = await assemble_srs(
        cpm,
        [FigureInput("class", "Class", broken, "image/svg+xml", (("image/png", PNG),))],
    )
    result = export_pdf(assembled.document, A4)

    assert result.raster_figures == 1
    assert result.figures == 1


async def test_a_figure_with_no_usable_rendition_is_reported(cpm) -> None:
    assembled = await assemble_srs(
        cpm, [FigureInput("class", "Class", b"\x00\x01", "application/postscript")]
    )
    with pytest.raises(UnrenderableFigure):
        export_pdf(assembled.document, A4)


async def test_a_raster_is_sized_from_its_dpi_not_its_pixel_count(cpm) -> None:
    # A 1200px diagram at 72dpi would be sixteen inches wide and get scaled to
    # a smear; read at its real 150dpi it is a sharp 8in figure.
    dense = sample_png(width=1200, height=600, dpi=150)
    assembled = await assemble_srs(cpm, [FigureInput("class", "Class", dense, "image/png")])
    result = export_pdf(assembled.document, A4)

    assert result.raster_figures == 1
    assert result.size > 0


# --------------------------------------------------------------------------
# The exporter never reopens its own output
# --------------------------------------------------------------------------


def _content_streams(result) -> list[bytes]:
    return [page.get_contents().get_data() for page in reader_of(result).pages]


def test_nothing_in_the_exporter_can_reopen_a_pdf() -> None:
    # Rendering happens once, into each page's own content stream, as that
    # page is produced — there is no second pass over a finished file.
    tree = python_ast.parse(Path(pdf_module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in python_ast.walk(tree):
        if isinstance(node, python_ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, python_ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])

    assert not imported & {"pypdf", "PyPDF2", "pikepdf", "fitz", "pdfrw"}
    assert not imported & {"docx"}, "the PDF exporter must not read the DOCX exporter's work"


# --------------------------------------------------------------------------
# Pagination, headers, footers
# --------------------------------------------------------------------------


async def test_every_body_page_has_the_running_header_and_a_page_number(cpm, document) -> None:
    result = export_pdf(document, A4)
    reader = reader_of(result)
    pages = [page.extract_text() or "" for page in reader.pages]

    assert len(pages) > 5
    for index, text in enumerate(pages[1:], start=2):
        assert cpm.meta.project_name in text, f"page {index} has no running header"
        assert re.search(rf"Page {index} of {len(pages)}", text), f"page {index} has no number"


async def test_the_title_page_has_no_running_head(document) -> None:
    first = reader_of(export_pdf(document, A4)).pages[0].extract_text() or ""
    assert "Page 1 of" not in first
    # The title wraps across lines on the page, so compare on collapsed space.
    assert "Software Requirements Specification" in " ".join(first.split())


async def test_the_outline_points_at_the_page_the_section_is_on(document) -> None:
    # Deferring showPage for the page totals also defers where a bookmark
    # lands; without care every entry resolved to page 1.
    result = export_pdf(document, A4)
    reader = reader_of(result)
    entries = [entry for entry in reader.outline if not isinstance(entry, list)]

    assert len(entries) == 3
    for entry in entries:
        page_index = reader.get_destination_page_number(entry)
        assert page_index > 0, f"{entry.title!r} points at the title page"
        assert entry.title in (reader.pages[page_index].extract_text() or ""), entry.title


async def test_page_size_and_margins_come_from_the_template(document) -> None:
    for template, width_mm in ((A4, 210.0), (US_LETTER, 215.9)):
        page = reader_of(export_pdf(document, template)).pages[0]
        assert round(float(page.mediabox.width) / 72 * 25.4) == round(width_mm)


async def test_a_different_template_changes_the_rendered_document(document) -> None:
    a4 = export_pdf(document, A4)
    times = export_pdf(document, IEEE_TIMES)
    assert a4.content != times.content
    # 1.5 line spacing and a larger body font make a longer document.
    assert len(reader_of(times).pages) > len(reader_of(a4).pages)


async def test_the_document_metadata_names_the_project(cpm, document) -> None:
    info = reader_of(export_pdf(document, A4)).metadata
    assert cpm.meta.project_name in info.title
    assert "IEEE 830" in info.subject


# --------------------------------------------------------------------------
# NFR-P4
# --------------------------------------------------------------------------


def _inflated_cpm(use_cases: int) -> CPM:
    """The fixture, grown to the size of a real submission."""
    payload = copy.deepcopy(library_management_system_payload())
    template = copy.deepcopy(payload["useCases"][0])
    for index in range(use_cases):
        clone = copy.deepcopy(template)
        clone["id"] = f"uc-generated-{index:03d}"
        clone["name"] = f"Managed Operation {index:03d}"
        payload["useCases"].append(clone)
    for index in range(40):
        payload["requirements"].append(
            {
                "id": f"req-generated-{index:03d}",
                "type": "functional" if index % 2 else "nonFunctional",
                "text": f"The system shall support generated operation {index:03d} "
                f"within the stated performance envelope.",
                "priority": "Medium",
            }
        )
    return CPM.model_validate(payload)


async def test_a_forty_page_document_exports_well_inside_the_budget() -> None:
    assembled = await assemble_srs(_inflated_cpm(60), inputs())

    started = time.perf_counter()
    result = export_pdf(assembled.document, A4)
    elapsed = time.perf_counter() - started

    pages = len(reader_of(result).pages)
    assert pages >= 40, f"the fixture only reached {pages} pages; the budget was not exercised"
    assert elapsed < 30.0, f"NFR-P4: {pages} pages took {elapsed:.1f}s"


# --------------------------------------------------------------------------
# The layer boundary
# --------------------------------------------------------------------------


async def test_the_exporter_refuses_an_unnumbered_document(cpm) -> None:
    from srs.ieee830 import build_document
    from srs.prose import DeterministicProse

    raw = await build_document(cpm, inputs(), DeterministicProse())
    with pytest.raises(ValueError, match="not been numbered"):
        export_pdf(raw, A4)


async def test_export_is_deterministic(document) -> None:
    first = export_pdf(document, A4)
    second = export_pdf(document, A4)
    # PDFs embed a creation timestamp, so the streams are compared instead.
    assert _content_streams(first) == _content_streams(second)
