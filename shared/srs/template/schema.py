"""Templates are configuration, not code.

A university template is a set of decisions about how a document looks and
what it must contain. None of those decisions belong in Python: adding a new
institution's format must be a row of JSON, not a deploy, or the product
cannot serve the fifty-first university without an engineer.

So this file describes the *shape* of a template and nothing about how one is
drawn. Every question a real template answers is a field here:

    where does the cover page put the logo, the enrolment number, the guide's
    name; is there a certificate page and what does it say; is the index a
    dotted table of contents or a three-column table with "Sr. No."; are
    figures numbered "Figure 7" or "Fig. 3.2"; does chapter 1 start on a fresh
    page; is the binding margin wider than the outer one

The schema was designed against the two most *different* templates that could
be found rather than the two easiest, because a schema that fits the easy ones
and needs an `if template.id == ...` for the hard one is not a schema. Where
the two disagree, the disagreement is a field with two values — never a branch.

Applied once, to the document AST, so the PDF and the DOCX get the same cover
page, the same certificate, the same numbering and the same captions. If each
exporter interpreted the template itself, the two deliverables would drift the
first time one of them was fixed.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Alignment = Literal["left", "center", "right", "justify"]


class TemplateBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    """`extra="forbid"` on purpose: a misspelt key that is silently ignored
    becomes "the template did not apply and nobody knows why" the night before
    a submission."""


# ---------------------------------------------------------------------------
# Page and type
# ---------------------------------------------------------------------------


class Page(TemplateBase):
    width_mm: float = 210.0
    height_mm: float = 297.0

    margin_top_mm: float = 25.4
    margin_bottom_mm: float = 25.4
    margin_inner_mm: float = 25.4
    """The binding edge. Bound reports need it wider — 1.5in is common — and
    calling it "left" makes that impossible to express for a duplex template."""
    margin_outer_mm: float = 25.4
    mirror_margins: bool = False

    @property
    def content_width_mm(self) -> float:
        return self.width_mm - self.margin_inner_mm - self.margin_outer_mm


class Style(TemplateBase):
    """One named look. Templates refer to these by name, never by value."""

    font: str = "Calibri"
    size_pt: float = 11.0
    bold: bool = False
    italic: bool = False
    all_caps: bool = False
    colour: str = "000000"
    align: Alignment = "left"
    line_spacing: float = 1.15
    space_before_pt: float = 0.0
    space_after_pt: float = 8.0
    keep_with_next: bool = False

    @field_validator("colour")
    @classmethod
    def _six_hex_digits(cls, value: str) -> str:
        if len(value) != 6 or any(c not in "0123456789abcdefABCDEF" for c in value):
            raise ValueError(f"colour must be six hex digits, got {value!r}")
        return value.upper()


REQUIRED_STYLES = (
    "body",
    "heading1",
    "heading2",
    "heading3",
    "caption",
    "cover_title",
    "cover_field",
    "index_entry",
)
"""Every template must define these, because the renderer will ask for them on
any document. Extra names are allowed and are how a template adds a look for a
block only it uses."""


# ---------------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------------


class SectionNumbering(TemplateBase):
    level_prefixes: tuple[str, ...] = ("", "", "", "")
    """Prepended per level. `("Chapter ", "", "")` gives "Chapter 1" then
    "1.1" — which is the single most common difference between a course
    hand-in and a bound project report, and is not expressible as a boolean."""

    separator: str = "."
    suffix: str = " "
    page_break_before_top_level: bool = False
    """Bound reports start every chapter on a fresh page. Course hand-ins run
    on."""


class CaptionNumbering(TemplateBase):
    scope: Literal["document", "chapter"] = "document"
    """"Figure 7" counts across the document; "Fig. 3.2" restarts inside each
    chapter. The second cannot be faked by relabelling the first."""

    label: str = "Figure"
    format: str = "{label} {number}: {caption}"
    position: Literal["above", "below"] = "below"
    style: str = "caption"

    @field_validator("format")
    @classmethod
    def _mentions_everything(cls, value: str) -> str:
        missing = [token for token in ("{number}", "{caption}") if token not in value]
        if missing:
            raise ValueError(f"caption format must include {', '.join(missing)}")
        return value


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------


class Block(TemplateBase):
    """One element on a front-matter page."""

    kind: Literal["text", "image", "spacer", "rule", "signatures", "table"]

    text: str = ""
    """May contain {tokens}: any declared field key, plus {project}, {title},
    {authors}, {date}, {version}."""

    style: str = "body"
    align: Alignment | None = None
    height_mm: float = 0.0

    field: str = ""
    """For an image block: which user-supplied field holds it (FR-15 logo)."""
    max_width_mm: float = 40.0
    max_height_mm: float = 40.0

    roles: tuple[str, ...] = ()
    """For a signatures block: the people who sign, laid out in one row."""

    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()

    @model_validator(mode="after")
    def _needs_its_own_content(self) -> "Block":
        needs = {
            "text": bool(self.text),
            "image": bool(self.field),
            "signatures": bool(self.roles),
            "table": bool(self.columns),
            "spacer": self.height_mm > 0,
            "rule": True,
        }
        if not needs[self.kind]:
            raise ValueError(f"a {self.kind!r} block has nothing to render")
        return self


class FrontPage(TemplateBase):
    kind: Literal["page"] = "page"
    id: str
    title: str = ""
    blocks: tuple[Block, ...]
    page_break_after: bool = True


class FrontIndex(TemplateBase):
    kind: Literal["index"] = "index"
    of: Literal["contents", "figures", "tables"]
    title: str
    layout: Literal["dotted", "table"] = "dotted"
    """A dotted table of contents, or a bordered table with headed columns.
    Indian project reports overwhelmingly use the second and it is not a
    styling variation of the first."""

    columns: tuple[str, ...] = ()
    max_depth: int = 3
    page_numbers: bool = True
    page_break_after: bool = True

    @model_validator(mode="after")
    def _table_layout_needs_columns(self) -> "FrontIndex":
        if self.layout == "table" and not self.columns:
            raise ValueError("a table index must name its columns")
        return self


FrontMatterItem = Annotated[FrontPage | FrontIndex, Field(discriminator="kind")]


# ---------------------------------------------------------------------------
# Running head, fields
# ---------------------------------------------------------------------------


class Running(TemplateBase):
    header_left: str = ""
    header_center: str = ""
    header_right: str = ""
    footer_left: str = ""
    footer_center: str = "Page {page} of {pages}"
    footer_right: str = ""
    rule_under_header: bool = False
    on_front_matter: bool = False
    """Most bound reports number the front matter in roman and the body in
    arabic; the simpler answer, and the one every template here agrees on, is
    to leave the cover and certificate bare."""

    @property
    def used(self) -> bool:
        return any(
            (
                self.header_left,
                self.header_center,
                self.header_right,
                self.footer_left,
                self.footer_center,
                self.footer_right,
            )
        )


class TemplateField(TemplateBase):
    """A value the template needs and the model cannot supply (FR-15)."""

    key: str
    label: str
    kind: Literal["text", "longtext", "year", "image"] = "text"
    required: bool = True
    placeholder: str = ""
    help: str = ""


# ---------------------------------------------------------------------------
# The template
# ---------------------------------------------------------------------------


class Template(TemplateBase):
    id: str
    name: str
    description: str = ""
    origin: str = ""
    """Where the format came from, so a future maintainer can check it against
    the real thing rather than against somebody's memory of it."""

    page: Page = Page()
    styles: dict[str, Style]
    section_numbering: SectionNumbering = SectionNumbering()
    figure_numbering: CaptionNumbering = CaptionNumbering()
    table_numbering: CaptionNumbering = CaptionNumbering(label="Table", position="above")
    front_matter: tuple[FrontMatterItem, ...] = ()
    running: Running = Running()
    fields: tuple[TemplateField, ...] = ()

    @model_validator(mode="after")
    def _styles_cover_what_the_renderer_asks_for(self) -> "Template":
        missing = [name for name in REQUIRED_STYLES if name not in self.styles]
        if missing:
            raise ValueError(f"template {self.id!r} defines no style for: {', '.join(missing)}")

        referenced = {self.figure_numbering.style, self.table_numbering.style}
        for item in self.front_matter:
            if isinstance(item, FrontPage):
                referenced.update(block.style for block in item.blocks)
        unknown = sorted(referenced - set(self.styles))
        if unknown:
            raise ValueError(
                f"template {self.id!r} refers to undefined styles: {', '.join(unknown)}"
            )
        return self

    @model_validator(mode="after")
    def _every_token_resolves(self) -> "Template":
        """A template may only mention fields it declares.

        This is the check that makes NFR-Q4 impossible to reach from a
        template: an unresolved `{course_code}` is caught when the template is
        loaded, not when a student opens the PDF.
        """
        known = BUILT_IN_TOKENS | {field.key for field in self.fields}
        used: set[str] = set()
        for item in self.front_matter:
            if isinstance(item, FrontPage):
                for block in item.blocks:
                    used.update(_tokens(block.text))
                    for row in block.rows:
                        for cell in row:
                            used.update(_tokens(cell))
        for value in (
            self.running.header_left,
            self.running.header_center,
            self.running.header_right,
            self.running.footer_left,
            self.running.footer_center,
            self.running.footer_right,
        ):
            used.update(_tokens(value))

        unknown = sorted(used - known)
        if unknown:
            raise ValueError(
                f"template {self.id!r} uses undeclared fields: {', '.join(unknown)}. "
                f"Declare them under `fields`, or use one of: {', '.join(sorted(known))}"
            )
        return self

    def style(self, name: str) -> Style:
        try:
            return self.styles[name]
        except KeyError:
            raise KeyError(
                f"template {self.id!r} has no style {name!r}; it defines "
                f"{', '.join(sorted(self.styles))}"
            ) from None

    def required_fields(self) -> list[TemplateField]:
        return [field for field in self.fields if field.required]


BUILT_IN_TOKENS = {
    "project",
    "title",
    "authors",
    "date",
    "version",
    "page",
    "pages",
}
"""Tokens every template may use without declaring them: they come from the
CPM and the document, not from the user."""


def _tokens(text: str) -> set[str]:
    import re

    return set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", text))


def load_template(payload: dict[str, Any]) -> Template:
    """Build a template from parsed JSON, refusing anything malformed.

    Loading is where a template is checked. A template that reaches the
    renderer has already been proved to define every style it uses, to name
    only fields it declares, and to have no unknown keys — so the renderer has
    no error handling for those cases and needs none.
    """
    return Template.model_validate(payload)
