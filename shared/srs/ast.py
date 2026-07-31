"""The document AST — one representation, several exporters.

This layer is deliberately ignorant of DOCX, PDF, HTML and of every library
that produces them. It knows about sections, paragraphs, figures, tables and
cross-references, and nothing about page size, fonts or XML.

The reason is the failure mode it prevents. The obvious way to ship two export
formats is to build one properly and derive the other — DOCX first, then "print
to PDF", or a PDF whose DOCX is a lossy re-parse. The derived format is then
permanently second class: its numbering comes from the first format's quirks,
its figures inherit whatever the first format needed, and a fix in one is a
translation problem in the other. A university that requires a .docx in a
mandated template and a PDF for the portal needs both to be right, and "we
converted it" is exactly the answer that produces a rejected submission.

So: assembly produces a `Document`, and every exporter is a pure function of
that `Document`. Neither export format can become a byproduct of the other,
because neither exists when the document is assembled.

Everything here is frozen and built from tuples. Numbering rebuilds the tree
rather than mutating it, so the same CPM plus the same figures always yields
the same document (FR-9), and an exporter cannot quietly renumber anything it
was handed.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace

# ---------------------------------------------------------------------------
# Inline content
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Text:
    value: str
    emphasis: bool = False


@dataclass(frozen=True)
class FigureRef:
    """A cross-reference to a figure, resolved during numbering.

    Stored as a reference rather than as the string "Figure 3" so that a
    sentence pointing at a figure and the figure's own caption cannot disagree.
    They are the same number by construction, not by discipline.
    """

    target_id: str
    resolved: str | None = None


@dataclass(frozen=True)
class TableRef:
    target_id: str
    resolved: str | None = None


@dataclass(frozen=True)
class SectionRef:
    target_id: str
    resolved: str | None = None


Inline = Text | FigureRef | TableRef | SectionRef

# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Paragraph:
    runs: tuple[Inline, ...]
    style: str = "body"
    """A style *name*, resolved by the exporter against the template. The AST
    never carries a font or a size: that is the difference between a document
    model and a rendering."""
    align: str | None = None


@dataclass(frozen=True)
class BulletList:
    items: tuple[tuple[Inline, ...], ...]


@dataclass(frozen=True)
class NumberedList:
    items: tuple[tuple[Inline, ...], ...]


@dataclass(frozen=True)
class Table:
    table_id: str
    caption: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    number: int | None = None
    display_number: str | None = None
    """What the reader sees: "7" in one template, "3.2" in another. The
    integer stays the running count; this is what the caption prints."""
    formatted_caption: str | None = None
    variant: str = "grid"
    cell_style: str = "body"

    @property
    def label(self) -> str:
        return f"Table {self.display_number or self.number}" if self.number else "Table"


@dataclass(frozen=True)
class Figure:
    """An embedded diagram (FR-16).

    Carries the rendered bytes and their media type. An exporter decides how to
    place them; nothing here knows that DOCX wants raster and PDF is happy with
    vector.
    """

    figure_id: str
    caption: str
    image: bytes
    mime: str
    alt: str
    diagram_type: str
    number: int | None = None
    display_number: str | None = None
    formatted_caption: str | None = None

    alternates: tuple[tuple[str, bytes], ...] = ()
    """The same picture in other formats, as (mime, bytes).

    One figure, several encodings, because the two exporters want different
    ones: PDF draws SVG as vector so the diagram stays sharp and its text
    stays selectable, while DOCX cannot embed SVG at all and needs the PNG.
    Carrying both here is what lets a single assembled document produce both
    files — if each export assembled its own document, AT-1's "identical
    content" would be a coincidence rather than a property.
    """

    @property
    def label(self) -> str:
        return f"Figure {self.display_number or self.number}" if self.number else "Figure"

    def rendition(self, preferred: Sequence[str]) -> tuple[str, bytes] | None:
        """The best available encoding for an exporter, or None if it has no
        format it can use — which is a failure to report, never to ignore."""
        available = {self.mime: self.image, **dict(self.alternates)}
        for mime in preferred:
            if mime in available:
                return mime, available[mime]
        return None


@dataclass(frozen=True)
class IndexEntry:
    number: str
    title: str
    target_id: str
    depth: int = 1


@dataclass(frozen=True)
class TableOfContents:
    entries: tuple[IndexEntry, ...] = ()
    title: str = "Contents"
    layout: str = "dotted"
    """"dotted" is a table of contents with leaders; "table" is a bordered
    grid with headed columns. Real templates ask for both and neither is a
    styling variant of the other."""
    columns: tuple[str, ...] = ()
    max_depth: int = 3
    page_numbers: bool = True


@dataclass(frozen=True)
class ListOfFigures:
    entries: tuple[IndexEntry, ...] = ()
    title: str = "List of Figures"
    layout: str = "dotted"
    columns: tuple[str, ...] = ()
    page_numbers: bool = True


@dataclass(frozen=True)
class ListOfTables:
    entries: tuple[IndexEntry, ...] = ()
    title: str = "List of Tables"
    layout: str = "dotted"
    columns: tuple[str, ...] = ()
    page_numbers: bool = True


@dataclass(frozen=True)
class Spacer:
    height_mm: float


@dataclass(frozen=True)
class Rule:
    """A horizontal line. Cover pages use them; nothing else does."""


@dataclass(frozen=True)
class PageBreak:
    pass


@dataclass(frozen=True)
class ImageBlock:
    """An image that is not a figure — a crest on a cover page (FR-15).

    Distinct from `Figure` because it is not numbered, not captioned and not
    listed: putting a logo through the figure machinery would make it
    "Figure 1" in every document that has one.
    """

    image: bytes
    mime: str
    max_width_mm: float = 40.0
    max_height_mm: float = 40.0
    align: str = "center"
    alt: str = ""


Block = (
    Paragraph
    | BulletList
    | NumberedList
    | Table
    | Figure
    | TableOfContents
    | ListOfFigures
    | ListOfTables
    | Spacer
    | Rule
    | PageBreak
    | ImageBlock
)

# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    section_id: str
    title: str
    blocks: tuple[Block, ...] = ()
    subsections: tuple["Section", ...] = ()
    number: str | None = None
    page_break_before: bool = False
    heading_style: str | None = None
    heading_text: str | None = None
    """What the heading actually reads. A template that prefixes "Chapter " at
    the top level composes it once, here, so the exporters and the contents
    page cannot disagree about what the heading says."""

    @property
    def heading(self) -> str:
        if self.heading_text:
            return self.heading_text
        return f"{self.number} {self.title}" if self.number else self.title


@dataclass(frozen=True)
class DocumentMeta:
    project_name: str
    version: str
    authors: tuple[str, ...] = ()
    created_at: str | None = None
    cpm_version_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class Document:
    title: str
    meta: DocumentMeta
    front_matter: tuple[Block, ...] = ()
    sections: tuple[Section, ...] = ()
    numbered: bool = False


# ---------------------------------------------------------------------------
# Builders — terse enough that the IEEE 830 layout stays readable
# ---------------------------------------------------------------------------


def para(*parts: str | Inline, style: str = "body", align: str | None = None) -> Paragraph:
    return Paragraph(
        runs=tuple(Text(p) if isinstance(p, str) else p for p in parts),
        style=style,
        align=align,
    )


def bullets(items: Sequence[str | Sequence[Inline]]) -> BulletList:
    return BulletList(items=tuple(_as_runs(item) for item in items))


def steps(items: Sequence[str | Sequence[Inline]]) -> NumberedList:
    return NumberedList(items=tuple(_as_runs(item) for item in items))


def _as_runs(item: str | Sequence[Inline]) -> tuple[Inline, ...]:
    if isinstance(item, str):
        return (Text(item),)
    return tuple(item)


# ---------------------------------------------------------------------------
# Traversal
# ---------------------------------------------------------------------------


def walk_sections(document: Document) -> Iterator[Section]:
    """Every section, depth-first, in reading order."""

    def descend(section: Section) -> Iterator[Section]:
        yield section
        for child in section.subsections:
            yield from descend(child)

    for section in document.sections:
        yield from descend(section)


def walk_blocks(document: Document) -> Iterator[tuple[str, Block]]:
    """Every block with the id of the section holding it, in reading order."""
    for block in document.front_matter:
        yield "<front>", block
    for section in walk_sections(document):
        for block in section.blocks:
            yield section.section_id, block


def figures(document: Document) -> list[Figure]:
    return [block for _, block in walk_blocks(document) if isinstance(block, Figure)]


def tables(document: Document) -> list[Table]:
    return [block for _, block in walk_blocks(document) if isinstance(block, Table)]


def iter_inlines(document: Document) -> Iterator[tuple[str, Inline]]:
    """Every inline run with the id of the section it sits in."""
    for section_id, block in walk_blocks(document):
        if isinstance(block, Paragraph):
            for run in block.runs:
                yield section_id, run
        elif isinstance(block, BulletList | NumberedList):
            for item in block.items:
                for run in item:
                    yield section_id, run


def iter_strings(document: Document) -> Iterator[tuple[str, str]]:
    """Every human-visible string with a location, for whole-document checks."""
    yield "title", document.title
    yield "meta.project", document.meta.project_name
    for author in document.meta.authors:
        yield "meta.author", author

    for section in walk_sections(document):
        yield f"{section.section_id}.title", section.title

    for section_id, block in walk_blocks(document):
        if isinstance(block, Paragraph):
            for run in block.runs:
                if isinstance(run, Text):
                    yield section_id, run.value
        elif isinstance(block, BulletList | NumberedList):
            for item in block.items:
                for run in item:
                    if isinstance(run, Text):
                        yield section_id, run.value
        elif isinstance(block, Table):
            yield f"{section_id}.table.caption", block.caption
            for column in block.columns:
                yield f"{section_id}.table.header", column
            for row in block.rows:
                for cell in row:
                    yield f"{section_id}.table.cell", cell
        elif isinstance(block, Figure):
            yield f"{section_id}.figure.caption", block.caption
            yield f"{section_id}.figure.alt", block.alt


def prose_text(document: Document) -> list[tuple[str, str]]:
    """Narrative text only — paragraphs and list items.

    Table cells and captions are excluded: those are CPM values copied
    verbatim, so checking them for name drift would only ever re-report the
    model's own contents.
    """
    collected: list[tuple[str, str]] = []
    for section_id, block in walk_blocks(document):
        if isinstance(block, Paragraph):
            value = "".join(run.value for run in block.runs if isinstance(run, Text))
            if value.strip():
                collected.append((section_id, value))
        elif isinstance(block, BulletList | NumberedList):
            for item in block.items:
                value = "".join(run.value for run in item if isinstance(run, Text))
                if value.strip():
                    collected.append((section_id, value))
    return collected


def find_section(document: Document, section_id: str) -> Section | None:
    for section in walk_sections(document):
        if section.section_id == section_id:
            return section
    return None


def add_block(document: Document, section_id: str, block: Block) -> Document:
    """Append a block to one section, returning a new document."""

    def rebuild(section: Section) -> Section:
        if section.section_id == section_id:
            return replace(section, blocks=section.blocks + (block,))
        return replace(section, subsections=tuple(rebuild(s) for s in section.subsections))

    return replace(document, sections=tuple(rebuild(s) for s in document.sections))


@dataclass(frozen=True)
class SectionDraft:
    """A mutable-feeling builder that still produces a frozen `Section`."""

    section_id: str
    title: str
    blocks: list[Block] = field(default_factory=list)
    subsections: list["SectionDraft"] = field(default_factory=list)

    def add(self, *blocks: Block) -> "SectionDraft":
        self.blocks.extend(b for b in blocks if b is not None)
        return self

    def sub(self, section_id: str, title: str) -> "SectionDraft":
        child = SectionDraft(section_id=section_id, title=title)
        self.subsections.append(child)
        return child

    def build(self) -> Section:
        return Section(
            section_id=self.section_id,
            title=self.title,
            blocks=tuple(self.blocks),
            subsections=tuple(child.build() for child in self.subsections),
        )
