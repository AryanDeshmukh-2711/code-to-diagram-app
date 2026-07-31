"""Templates are configuration, and the two extremes prove it.

The claim under test is not "templates work". It is that the two most
dissimilar formats on file are expressed in *one* schema, take effect through
*one* code path, and that a third format is a file rather than a deploy. So the
assertions here mostly compare the two extremes against each other: wherever
they differ, the difference must come from config.
"""

import json

import pytest
from conftest import sample_png

from cpm.fixtures import load_library_management_system
from srs.assemble import assemble_srs
from srs.ast import ImageBlock, PageBreak, Rule, Spacer, figures, tables, walk_sections
from srs.export.docx import export_docx
from srs.export.pdf import export_pdf
from srs.ieee830 import CAPTIONS, FigureInput
from srs.template.apply import (
    BUILTIN_DIR,
    MissingTemplateFields,
    TemplateInputs,
    apply_template,
    available_templates,
    get_template,
    load_template_file,
    to_document_template,
)
from srs.template.schema import Template, load_template

PNG = sample_png()

BOUND = TemplateInputs(
    values={
        "institution": "University of Mumbai",
        "department": "Department of Computer Engineering",
        "course_code": "CSC802",
        "student_name": "A. V. Deshmukh",
        "enrolment_number": "2021CS0142",
        "guide_name": "Prof. R. Kulkarni",
        "academic_year": "2025-26",
    },
    images={"logo": (sample_png(120, 120), "image/png")},
)
COURSE = TemplateInputs(
    values={
        "institution": "Example University",
        "course_code": "SE3040",
        "student_name": "A. V. Deshmukh",
    }
)


@pytest.fixture
def cpm():
    return load_library_management_system()


@pytest.fixture
async def document(cpm):
    figures_in = [
        FigureInput(t, CAPTIONS[t], PNG, "image/png") for t in ("class", "use_case", "sequence")
    ]
    return (await assemble_srs(cpm, figures_in)).document


# --------------------------------------------------------------------------
# One schema, two extremes
# --------------------------------------------------------------------------


def test_the_two_most_different_templates_load_from_the_same_schema() -> None:
    bound = get_template("bound-project-report")
    course = get_template("course-hand-in")

    assert isinstance(bound, Template) and isinstance(course, Template)
    # Every difference below is a value, not a branch.
    assert bound.page.margin_inner_mm != bound.page.margin_outer_mm
    assert course.page.margin_inner_mm == course.page.margin_outer_mm
    assert bound.section_numbering.level_prefixes[0] == "Chapter "
    assert course.section_numbering.level_prefixes[0] == ""
    assert bound.figure_numbering.scope == "chapter"
    assert course.figure_numbering.scope == "document"
    assert [i for i in bound.front_matter if i.kind == "page" and i.id == "certificate"]
    assert not [i for i in course.front_matter if i.kind == "page" and i.id == "certificate"]
    assert [i for i in bound.front_matter if i.kind == "index"][0].layout == "table"
    assert [i for i in course.front_matter if i.kind == "index"][0].layout == "dotted"


def test_the_applier_names_no_template(cpm) -> None:
    # The failure this guards: a schema that fits the easy templates and grows
    # an `if template.id == ...` for the hard one.
    import ast
    from pathlib import Path

    import srs.template.apply as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Code only. The module docstring names an id as the example of what must
    # never appear, and a guard that flags its own explanation gets deleted.
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    docstrings = {
        ast.get_docstring(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    for template_id in available_templates():
        assert template_id not in (literals - docstrings), (
            f"the applier mentions {template_id!r} in code"
        )
    comparisons = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Attribute)
        and node.left.attr == "id"
    ]
    assert not comparisons, "the applier branches on a template id"


async def test_the_two_extremes_produce_genuinely_different_documents(document) -> None:
    bound = apply_template(document, get_template("bound-project-report"), BOUND)
    course = apply_template(document, get_template("course-hand-in"), COURSE)

    bound_headings = [s.heading for s in walk_sections(bound)]
    course_headings = [s.heading for s in walk_sections(course)]
    assert bound_headings[0] == "Chapter 1 Introduction"
    assert course_headings[0] == "1 Introduction"

    assert [f.display_number for f in figures(bound)] == ["2.1", "3.1", "3.2"]
    assert [f.display_number for f in figures(course)] == ["1", "2", "3"]
    assert figures(bound)[0].formatted_caption.startswith("Fig. 2.1 ")
    assert figures(course)[0].formatted_caption.startswith("Figure 1: ")

    assert any(isinstance(b, ImageBlock) for b in bound.front_matter)
    assert not any(isinstance(b, ImageBlock) for b in course.front_matter)


async def test_the_certificate_page_carries_every_supplied_field(document) -> None:
    bound = apply_template(document, get_template("bound-project-report"), BOUND)
    text = " ".join(
        run.value
        for block in bound.front_matter
        if hasattr(block, "runs")
        for run in block.runs
        if hasattr(run, "value")
    )
    for value in BOUND.values.values():
        assert value in text, value
    assert "{" not in text, "a token survived into the document"


async def test_chapters_start_on_a_fresh_page_only_where_asked(document) -> None:
    bound = apply_template(document, get_template("bound-project-report"), BOUND)
    course = apply_template(document, get_template("course-hand-in"), COURSE)
    assert all(s.page_break_before for s in bound.sections)
    assert not any(s.page_break_before for s in course.sections)


async def test_uncaptioned_layout_tables_are_not_numbered_as_exhibits(document) -> None:
    # The signature block on the certificate is a table. Numbering it would put
    # "Table 1" on a certificate and list it in the List of Tables.
    bound = apply_template(document, get_template("bound-project-report"), BOUND)
    numbered = [t for t in tables(bound) if t.number]
    assert all(t.caption for t in numbered)
    assert any(not t.caption for t in tables(bound)), "no layout table in this fixture"


# --------------------------------------------------------------------------
# FR-15: the user's fields
# --------------------------------------------------------------------------


async def test_a_missing_required_field_is_refused_before_anything_renders(document) -> None:
    with pytest.raises(MissingTemplateFields) as excinfo:
        apply_template(document, get_template("bound-project-report"), TemplateInputs())

    message = str(excinfo.value)
    for key in ("institution", "enrolment_number", "guide_name"):
        assert key in message
    assert "review stage" in message


async def test_every_missing_field_is_named_at_once(document) -> None:
    partial = TemplateInputs(values={"institution": "X"})
    with pytest.raises(MissingTemplateFields) as excinfo:
        apply_template(document, get_template("bound-project-report"), partial)
    assert len(excinfo.value.missing) >= 5


async def test_an_optional_logo_that_is_absent_leaves_no_hole(document) -> None:
    without_logo = TemplateInputs(values=dict(BOUND.values))
    applied = apply_template(document, get_template("bound-project-report"), without_logo)
    assert not any(isinstance(b, ImageBlock) for b in applied.front_matter)
    assert any(isinstance(b, Spacer) for b in applied.front_matter)


def test_a_template_may_not_mention_a_field_it_does_not_declare() -> None:
    payload = json.loads((BUILTIN_DIR / "course_hand_in.json").read_text(encoding="utf-8"))
    payload["front_matter"][0]["blocks"].append(
        {"kind": "text", "text": "{supervisor}", "style": "cover_field"}
    )
    with pytest.raises(ValueError, match="supervisor"):
        load_template(payload)


def test_a_template_may_not_use_a_style_it_does_not_define() -> None:
    payload = json.loads((BUILTIN_DIR / "course_hand_in.json").read_text(encoding="utf-8"))
    payload["front_matter"][0]["blocks"][1]["style"] = "grandiose"
    with pytest.raises(ValueError, match="grandiose"):
        load_template(payload)


def test_a_misspelt_setting_is_refused_rather_than_ignored() -> None:
    payload = json.loads((BUILTIN_DIR / "course_hand_in.json").read_text(encoding="utf-8"))
    payload["margin_top"] = 30
    with pytest.raises(ValueError):
        load_template(payload)


# --------------------------------------------------------------------------
# DoD: a new template is config only
# --------------------------------------------------------------------------


async def test_a_brand_new_template_needs_no_code(document, tmp_path) -> None:
    """The whole claim, tested end to end.

    A template that has never been seen — its own page size, fonts, numbering
    and cover — is written to a file and rendered to both formats. Nothing is
    imported, registered or deployed.
    """
    payload = json.loads((BUILTIN_DIR / "course_hand_in.json").read_text(encoding="utf-8"))
    payload["id"] = "invented-polytechnic"
    payload["name"] = "Invented Polytechnic"
    payload["page"]["width_mm"] = 200.0
    payload["page"]["height_mm"] = 260.0
    payload["section_numbering"]["level_prefixes"] = ["Part ", "", "", ""]
    payload["figure_numbering"]["label"] = "Illustration"
    payload["figure_numbering"]["format"] = "{label} {number} — {caption}"
    for style in payload["styles"].values():
        style["font"] = "Courier New"

    path = tmp_path / "invented.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    template = load_template_file(path)
    applied = apply_template(document, template, COURSE)
    resolved = to_document_template(template, COURSE)

    assert [s.heading for s in walk_sections(applied)][0] == "Part 1 Introduction"
    assert figures(applied)[0].formatted_caption.startswith("Illustration 1 — ")

    docx = export_docx(applied, resolved)
    pdf = export_pdf(applied, resolved)
    assert docx.size > 0 and pdf.size > 0

    from io import BytesIO

    from docx import Document as DocxDocument
    from pypdf import PdfReader

    reopened = DocxDocument(BytesIO(docx.content))
    assert round(reopened.sections[0].page_width.mm) == 200
    assert 'w:ascii="Courier New"' in _styles_xml(docx.content)
    page = PdfReader(BytesIO(pdf.content)).pages[0]
    assert round(float(page.mediabox.width) / 72 * 25.4) == 200


def _styles_xml(blob: bytes) -> str:
    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(blob)) as archive:
        return archive.read("word/styles.xml").decode("utf-8")


def test_three_templates_ship() -> None:
    templates = available_templates()
    assert set(templates) == {"bound-project-report", "course-hand-in", "ieee-830-plain"}
    for template in templates.values():
        assert template.origin, f"{template.id} does not say where its format came from"


def test_templates_are_read_from_disk_every_time(tmp_path, monkeypatch) -> None:
    # A file dropped in is available to the next run. Caching the directory at
    # import time would quietly turn "add a template" back into a deploy.
    import srs.template.apply as module

    monkeypatch.setattr(module, "BUILTIN_DIR", tmp_path)
    assert available_templates() == {}

    payload = json.loads((BUILTIN_DIR / "course_hand_in.json").read_text(encoding="utf-8"))
    payload["id"] = "dropped-in"
    (tmp_path / "dropped.json").write_text(json.dumps(payload), encoding="utf-8")

    assert "dropped-in" in available_templates()


# --------------------------------------------------------------------------
# Both exporters, one treatment
# --------------------------------------------------------------------------


async def test_both_exporters_render_every_front_matter_block(document) -> None:
    # An unhandled block would be missing from one format and present in the
    # other. Both exporters now refuse rather than skip.
    applied = apply_template(document, get_template("bound-project-report"), BOUND)
    kinds = {type(block) for block in applied.front_matter}
    assert {Spacer, Rule, PageBreak, ImageBlock} <= kinds

    resolved = to_document_template(get_template("bound-project-report"), BOUND)
    assert export_docx(applied, resolved).size > 0
    assert export_pdf(applied, resolved).size > 0


async def test_an_unknown_block_is_refused_by_both_exporters(document) -> None:
    from dataclasses import dataclass, replace

    @dataclass(frozen=True)
    class Unknown:
        pass

    broken = replace(document, front_matter=(Unknown(),))
    resolved = to_document_template(get_template("course-hand-in"), COURSE)

    with pytest.raises(TypeError, match="Unknown"):
        export_docx(broken, resolved)
    with pytest.raises(TypeError, match="Unknown"):
        export_pdf(broken, resolved)


async def test_the_template_reaches_the_page_setup_of_both_formats(document) -> None:
    from io import BytesIO

    from docx import Document as DocxDocument
    from pypdf import PdfReader

    for template_id, inputs, width in (
        ("bound-project-report", BOUND, 210),
        ("course-hand-in", COURSE, 216),
    ):
        template = get_template(template_id)
        applied = apply_template(document, template, inputs)
        resolved = to_document_template(template, inputs)

        docx_page = DocxDocument(BytesIO(export_docx(applied, resolved).content)).sections[0]
        pdf_page = PdfReader(BytesIO(export_pdf(applied, resolved).content)).pages[0]

        assert round(docx_page.page_width.mm) == width
        assert round(float(pdf_page.mediabox.width) / 72 * 25.4) == width
