"""Applying a template to the document AST.

This is the single place a template takes effect, and that is the point. The
cover page, the certificate, the index layout, the numbering scheme and the
caption wording all become *AST* — ordinary blocks in the same tree the
exporters already render — so the PDF and the DOCX receive identical treatment
without either of them containing a line of template logic. If each exporter
interpreted the template, the two deliverables would diverge the first time
one of them was fixed, and AT-1 would start failing for reasons nobody could
localise.

The other half of the design is that nothing here knows any template by name.
There is no `if template.id == "bound-project-report"`. Every difference
between the two most dissimilar templates on file — a certificate page, a
three-column INDEX table, "Fig. 3.2" against "Figure 7", a 38mm binding
margin, chapters that start on a fresh page — is a value read from config. A
new institution is a JSON file, not a deploy.
"""

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from srs.ast import (
    Document,
    ImageBlock,
    ListOfFigures,
    ListOfTables,
    PageBreak,
    Paragraph,
    Rule,
    Spacer,
    Table,
    TableOfContents,
    Text,
)
from srs.numbering import CaptionScheme, NumberingScheme, number
from srs.template.schema import Block, FrontIndex, FrontPage, Template, load_template

BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"


class MissingTemplateFields(ValueError):
    """The template needs values the user has not supplied (FR-15).

    Raised before anything is rendered, naming every missing field at once —
    a student should not discover a second missing field after fixing the
    first.
    """

    def __init__(self, template_id: str, missing: list[str]) -> None:
        super().__init__(
            f"template {template_id!r} needs values for: {', '.join(missing)}. "
            f"Supply them at the review stage before generating."
        )
        self.missing = missing


@dataclass
class TemplateInputs:
    """What the user supplied for this document."""

    values: dict[str, str] = field(default_factory=dict)
    images: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    """key -> (bytes, mime). Uploads, kept apart from text so a caller cannot
    accidentally interpolate a logo into a sentence."""


def available_templates() -> dict[str, Template]:
    """Every template on disk. Read at call time, not at import time.

    A template dropped into the directory is available to the next run. That
    is the whole "no deploy" claim, and caching the directory at import would
    quietly break it.
    """
    found: dict[str, Template] = {}
    for path in sorted(BUILTIN_DIR.glob("*.json")):
        template = load_template(json.loads(path.read_text(encoding="utf-8")))
        found[template.id] = template
    return found


def load_template_file(path: str | Path) -> Template:
    """Load a template from anywhere — a file, an upload, a database row."""
    return load_template(json.loads(Path(path).read_text(encoding="utf-8")))


def get_template(template_id: str) -> Template:
    templates = available_templates()
    try:
        return templates[template_id]
    except KeyError:
        raise KeyError(
            f"no template {template_id!r}; available: {', '.join(sorted(templates))}"
        ) from None


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def _token_values(document: Document, inputs: TemplateInputs) -> dict[str, str]:
    meta = document.meta
    return {
        "project": meta.project_name,
        "title": document.title,
        "authors": ", ".join(meta.authors),
        "version": meta.version,
        "date": (meta.created_at or datetime.now(UTC).isoformat())[:10],
        **inputs.values,
    }


_TOKEN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _fill(text: str, values: dict[str, str]) -> str:
    """Substitute tokens, leaving nothing behind.

    A token with no value would survive into the document and be caught by the
    NFR-Q4 placeholder assertion — correct, but far too late to be useful. The
    field check runs first so the failure names the field, not the artefact.
    """
    return _TOKEN.sub(lambda match: values.get(match.group(1), match.group(0)), text)


def check_fields(template: Template, inputs: TemplateInputs) -> None:
    missing = [
        f"{item.key} ({item.label})"
        for item in template.required_fields()
        if item.kind == "image"
        and item.key not in inputs.images
        or item.kind != "image"
        and not inputs.values.get(item.key, "").strip()
    ]
    if missing:
        raise MissingTemplateFields(template.id, missing)


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------


def _block_to_ast(block: Block, values: dict[str, str], inputs: TemplateInputs):
    if block.kind == "text":
        return [
            Paragraph(
                runs=(Text(_fill(block.text, values)),),
                style=block.style,
                align=block.align,
            )
        ]
    if block.kind == "spacer":
        return [Spacer(height_mm=block.height_mm)]
    if block.kind == "rule":
        return [Rule()]
    if block.kind == "image":
        upload = inputs.images.get(block.field)
        if upload is None:
            # Optional and not supplied: leave the space rather than a gap
            # where a crest should be.
            return []
        payload, mime = upload
        return [
            ImageBlock(
                image=payload,
                mime=mime,
                max_width_mm=block.max_width_mm,
                max_height_mm=block.max_height_mm,
                align=block.align or "center",
                alt=block.field,
            )
        ]
    if block.kind == "signatures":
        # One row, one column per signatory, no borders. A signature block is
        # a table of empty space with names under it; drawing it as anything
        # else makes the two exporters disagree about where the line sits.
        return [
            Table(
                table_id=f"sig-{'-'.join(role.lower().replace(' ', '-') for role in block.roles)}",
                caption="",
                columns=tuple(" " for _ in block.roles),
                rows=(tuple(f"_____________________\n{role}" for role in block.roles),),
                variant="plain",
                cell_style=block.style,
            )
        ]
    if block.kind == "table":
        return [
            Table(
                table_id=f"front-{abs(hash(block.columns)) % 10**8}",
                caption="",
                columns=tuple(block.columns),
                rows=tuple(tuple(_fill(cell, values) for cell in row) for row in block.rows),
                variant="grid",
                cell_style=block.style,
            )
        ]
    raise ValueError(f"unhandled template block kind {block.kind!r}")


def _index_to_ast(item: FrontIndex):
    common = {
        "title": item.title,
        "layout": item.layout,
        "columns": tuple(item.columns),
        "page_numbers": item.page_numbers,
    }
    if item.of == "contents":
        return TableOfContents(max_depth=item.max_depth, **common)
    if item.of == "figures":
        return ListOfFigures(**common)
    return ListOfTables(**common)


def _front_matter(template: Template, document: Document, inputs: TemplateInputs) -> tuple:
    values = _token_values(document, inputs)
    blocks: list = []
    for item in template.front_matter:
        if isinstance(item, FrontPage):
            for block in item.blocks:
                blocks.extend(_block_to_ast(block, values, inputs))
        else:
            blocks.append(_index_to_ast(item))
        if item.page_break_after:
            blocks.append(PageBreak())
    return tuple(blocks)


# ---------------------------------------------------------------------------
# Numbering and headings
# ---------------------------------------------------------------------------


def numbering_scheme(template: Template) -> NumberingScheme:
    return NumberingScheme(
        level_prefixes=tuple(template.section_numbering.level_prefixes),
        separator=template.section_numbering.separator,
        suffix=template.section_numbering.suffix,
        figures=CaptionScheme(
            scope=template.figure_numbering.scope,
            label=template.figure_numbering.label,
            format=template.figure_numbering.format,
        ),
        tables=CaptionScheme(
            scope=template.table_numbering.scope,
            label=template.table_numbering.label,
            format=template.table_numbering.format,
        ),
    )


def _apply_page_breaks(document: Document, template: Template) -> Document:
    """Chapters on fresh pages, where the template asks for it."""
    if not template.section_numbering.page_break_before_top_level:
        return document
    return replace(
        document,
        sections=tuple(replace(s, page_break_before=True) for s in document.sections),
    )


# ---------------------------------------------------------------------------


def apply_template(
    document: Document,
    template: Template,
    inputs: TemplateInputs | None = None,
) -> Document:
    """Return the document as this template says it should be.

    Numbers it too: a template that changes the numbering scheme has to be
    applied before the tree is numbered, and doing both here removes the
    possibility of applying one without the other.
    """
    inputs = inputs or TemplateInputs()
    check_fields(template, inputs)

    with_front = replace(document, front_matter=_front_matter(template, document, inputs))
    numbered = number(with_front, numbering_scheme(template))
    return _apply_page_breaks(numbered, template)


def describe(template: Template) -> dict[str, Any]:
    """A summary for the review screen: what this template will ask for."""
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "page": f"{template.page.width_mm:.0f}x{template.page.height_mm:.0f}mm",
        "fields": [
            {
                "key": item.key,
                "label": item.label,
                "kind": item.kind,
                "required": item.required,
                "placeholder": item.placeholder,
                "help": item.help,
            }
            for item in template.fields
        ],
        "frontMatter": [
            item.id if isinstance(item, FrontPage) else f"{item.of} ({item.layout})"
            for item in template.front_matter
        ],
    }


def to_document_template(template: Template, inputs: "TemplateInputs | None" = None):
    """The exporter-facing view of a configured template.

    One conversion, used by both exporters, so a template cannot mean one
    thing in the PDF and another in the DOCX. Everything an exporter needs to
    lay out a page comes through here; nothing reads the JSON directly.
    """
    from srs.export.template import DocumentTemplate, Margins

    # Running heads carry the user's fields — a course code, an institution.
    # They are resolved here, where the values live, so the exporters receive
    # finished text and only {page}/{pages} are left for them to compute.
    values = dict(inputs.values) if inputs else {}
    values.setdefault("project", "")

    body = template.style("body")
    heading1 = template.style("heading1")
    caption = template.style("caption")

    return DocumentTemplate(
        name=template.name,
        page_width_mm=template.page.width_mm,
        page_height_mm=template.page.height_mm,
        margins=Margins(
            top_mm=template.page.margin_top_mm,
            bottom_mm=template.page.margin_bottom_mm,
            left_mm=template.page.margin_inner_mm,
            right_mm=template.page.margin_outer_mm,
        ),
        body_font=body.font,
        body_size_pt=body.size_pt,
        line_spacing=body.line_spacing,
        space_after_pt=body.space_after_pt,
        heading_font=heading1.font,
        heading_sizes_pt=(
            template.style("heading1").size_pt,
            template.style("heading2").size_pt,
            template.style("heading3").size_pt,
        ),
        heading_colour=heading1.colour,
        caption_font=caption.font,
        caption_size_pt=caption.size_pt,
        caption_italic=caption.italic,
        header_text=_fill_running(_running_slot(template, "header"), values),
        footer_text=_fill_running(_running_slot(template, "footer"), values),
        show_header_rule=template.running.rule_under_header,
        title_page=False,
        styles=dict(template.styles),
    )


def _fill_running(text: str, values: dict[str, str]) -> str:
    """Fill everything except the two tokens only a paginator can answer."""
    return _TOKEN.sub(
        lambda match: (
            match.group(0)
            if match.group(1) in ("page", "pages")
            else values.get(match.group(1), match.group(0))
        ),
        text,
    )


def _running_slot(template: Template, which: str) -> str:
    """Collapse the three slots into the single string the exporters take.

    Deliberately lossy and deliberately visible: the exporters currently place
    one header and one footer, so a template asking for left *and* right gets
    them joined rather than silently losing one.
    """
    running = template.running
    parts = [
        getattr(running, f"{which}_left"),
        getattr(running, f"{which}_center"),
        getattr(running, f"{which}_right"),
    ]
    return "   ".join(part for part in parts if part)
