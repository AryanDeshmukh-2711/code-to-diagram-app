"""Section numbers, figure numbers, and the index tables that must match them.

Everything numbered in the document is numbered here, once, in a single pass
over the tree — and the table of contents, list of figures and list of tables
are built from the *result* of that pass rather than assembled alongside it.

That is the whole point. An index that is written next to the content it
indexes drifts the first time a section moves; an index derived from the
numbered tree cannot disagree with the tree, because there is only one source
of the numbers. The same applies to cross-references: a sentence says
`FigureRef("fig-class")`, not "Figure 3", and gets its text from the figure's
assigned number.

Numbering is a pure function. `number(document)` returns a new document and
leaves its input untouched, so running it twice is not a way to end up with
"Figure 1 1".
"""

from dataclasses import dataclass, field, replace

from srs.ast import (
    BulletList,
    Document,
    Figure,
    FigureRef,
    IndexEntry,
    Inline,
    ListOfFigures,
    ListOfTables,
    NumberedList,
    Paragraph,
    Section,
    SectionRef,
    Table,
    TableOfContents,
    TableRef,
    Text,
    walk_sections,
)


@dataclass(frozen=True)
class CaptionScheme:
    """How one kind of caption is numbered and worded.

    A local type rather than the template's own, so numbering depends on
    nothing above it: the template layer converts, and this file stays a pure
    function of the tree plus a handful of strings.
    """

    scope: str = "document"
    label: str = "Figure"
    format: str = "{label} {number}: {caption}"

    def render(self, number: str, caption: str) -> str:
        return self.format.format(label=self.label, number=number, caption=caption)


@dataclass(frozen=True)
class NumberingScheme:
    """Everything a template decides about numbers.

    The default is the plain document-wide scheme, so a caller with no template
    gets exactly the behaviour it had before templates existed.
    """

    level_prefixes: tuple[str, ...] = ("", "", "", "")
    separator: str = "."
    suffix: str = " "
    figures: CaptionScheme = field(default_factory=CaptionScheme)
    tables: CaptionScheme = field(
        default_factory=lambda: CaptionScheme(label="Table", format="{label} {number}: {caption}")
    )

    def prefix(self, level: int) -> str:
        index = min(level, len(self.level_prefixes)) - 1
        return self.level_prefixes[index] if index >= 0 else ""


DEFAULT_SCHEME = NumberingScheme()


class UnresolvedReference(LookupError):
    """A cross-reference pointing at something the document does not contain.

    Loud rather than silent: a dangling reference rendered as "see Figure ?"
    is exactly the kind of blemish that gets a submission handed back, and it
    is invisible in a spot check of a forty-page document.
    """


def number(document: Document, scheme: NumberingScheme = DEFAULT_SCHEME) -> Document:
    """Assign every number in the document and resolve every reference."""
    sections = _number_sections(document.sections, scheme=scheme)
    numbered = replace(document, sections=sections)

    figure_numbers, table_numbers = _assign_captioned(numbered, scheme)
    numbered = _apply_captions(numbered, figure_numbers, table_numbers, scheme)

    section_numbers = {s.section_id: (s.number or "", s.title) for s in walk_sections(numbered)}
    numbered = _resolve_references(numbered, figure_numbers, table_numbers, section_numbers, scheme)
    numbered = _fill_indexes(numbered)

    return replace(numbered, numbered=True)


# ---------------------------------------------------------------------------


def _number_sections(
    sections: tuple[Section, ...],
    prefix: str = "",
    scheme: NumberingScheme = DEFAULT_SCHEME,
    level: int = 1,
) -> tuple[Section, ...]:
    out = []
    for index, section in enumerate(sections, start=1):
        label = f"{prefix}{index}" if not prefix else f"{prefix}{scheme.separator}{index}"
        # The heading is composed here, once, including any level prefix. The
        # contents page is then built from the same string, so "Chapter 1
        # Introduction" cannot appear in the body and "1 Introduction" in the
        # index.
        heading = f"{scheme.prefix(level)}{label}{scheme.suffix}{section.title}"
        out.append(
            replace(
                section,
                number=label,
                heading_text=heading,
                heading_style=f"heading{min(level, 3)}",
                subsections=_number_sections(section.subsections, label, scheme, level + 1),
            )
        )
    return tuple(out)


def _assign_captioned(
    document: Document, scheme: NumberingScheme = DEFAULT_SCHEME
) -> tuple[dict[str, str], dict[str, str]]:
    """Walk in reading order and hand out figure and table numbers.

    Sequential across the whole document, not restarted per chapter: "Figure 7"
    is unambiguous when a marker is looking for the seventh figure, and per-
    chapter numbering is where off-by-one errors hide.
    """
    figure_numbers: dict[str, str] = {}
    table_numbers: dict[str, str] = {}
    within: dict[tuple[str, str], int] = {}

    def next_number(kind: str, chapter: str, seen: dict) -> str:
        caption_scheme = scheme.figures if kind == "figure" else scheme.tables
        if caption_scheme.scope == "chapter" and chapter:
            # "Fig. 3.2" is the second figure of chapter 3. Restarting inside
            # each chapter is not a relabelling of a document-wide count, so
            # the counter has to be kept per chapter.
            within[(kind, chapter)] = within.get((kind, chapter), 0) + 1
            return f"{chapter}{scheme.separator}{within[(kind, chapter)]}"
        return str(len(seen) + 1)

    for chapter, block in _blocks_in_order(document):
        if isinstance(block, Figure) and block.figure_id not in figure_numbers:
            figure_numbers[block.figure_id] = next_number("figure", chapter, figure_numbers)
        elif isinstance(block, Table) and block.caption and block.table_id not in table_numbers:
            # An uncaptioned table is layout, not an exhibit. A signature block
            # on a certificate page is a table; numbering it would put
            # "Table 1: " on a cover and list it in the List of Tables.
            table_numbers[block.table_id] = next_number("table", chapter, table_numbers)

    return figure_numbers, table_numbers


def _blocks_in_order(document: Document):
    """Every block in reading order, tagged with its top-level section number.

    The chapter number rather than the section id, because that is what
    chapter-scoped caption numbering needs and nothing else asks for.
    """
    for block in document.front_matter:
        yield "", block

    def descend(section: Section, chapter: str):
        for block in section.blocks:
            yield chapter, block
        for child in section.subsections:
            yield from descend(child, chapter)

    for section in document.sections:
        yield from descend(section, section.number or "")


def _apply_captions(
    document: Document,
    figure_numbers: dict[str, str],
    table_numbers: dict[str, str],
    scheme: NumberingScheme = DEFAULT_SCHEME,
) -> Document:
    sequence: dict[str, dict[str, int]] = {"figure": {}, "table": {}}
    for _, block in _blocks_in_order(document):
        if isinstance(block, Figure):
            sequence["figure"].setdefault(block.figure_id, len(sequence["figure"]) + 1)
        elif isinstance(block, Table) and block.caption:
            sequence["table"].setdefault(block.table_id, len(sequence["table"]) + 1)

    def fix(block):
        if isinstance(block, Figure):
            display = figure_numbers.get(block.figure_id)
            return replace(
                block,
                number=sequence["figure"].get(block.figure_id),
                display_number=display,
                formatted_caption=(
                    scheme.figures.render(display, block.caption) if display else None
                ),
            )
        if isinstance(block, Table):
            display = table_numbers.get(block.table_id)
            return replace(
                block,
                number=sequence["table"].get(block.table_id),
                display_number=display,
                formatted_caption=(
                    scheme.tables.render(display, block.caption) if display else None
                ),
            )
        return block

    return _map_blocks(document, fix)


def _resolve_references(
    document: Document,
    figure_numbers: dict[str, str],
    table_numbers: dict[str, str],
    section_numbers: dict[str, tuple[str, str]],
    scheme: NumberingScheme = DEFAULT_SCHEME,
) -> Document:
    missing: list[str] = []

    def resolve(run: Inline) -> Inline:
        if isinstance(run, FigureRef):
            found = figure_numbers.get(run.target_id)
            if found is None:
                missing.append(f"figure {run.target_id!r}")
                return run
            return replace(run, resolved=f"{scheme.figures.label} {found}")
        if isinstance(run, TableRef):
            found = table_numbers.get(run.target_id)
            if found is None:
                missing.append(f"table {run.target_id!r}")
                return run
            return replace(run, resolved=f"{scheme.tables.label} {found}")
        if isinstance(run, SectionRef):
            entry = section_numbers.get(run.target_id)
            if entry is None:
                missing.append(f"section {run.target_id!r}")
                return run
            return replace(run, resolved=f"Section {entry[0]}")
        return run

    def fix(block):
        if isinstance(block, Paragraph):
            return replace(block, runs=tuple(resolve(run) for run in block.runs))
        if isinstance(block, BulletList | NumberedList):
            return replace(
                block, items=tuple(tuple(resolve(run) for run in item) for item in block.items)
            )
        return block

    result = _map_blocks(document, fix)
    if missing:
        raise UnresolvedReference(
            "the document references something it does not contain: " + ", ".join(sorted(missing))
        )
    return result


def _fill_indexes(document: Document) -> Document:
    depth_limit = max(
        (
            block.max_depth
            for _, block in _blocks_in_order(document)
            if isinstance(block, TableOfContents)
        ),
        default=9,
    )
    contents = tuple(
        IndexEntry(
            number=section.number or "",
            title=section.title,
            target_id=section.section_id,
            depth=len((section.number or "").split(".")),
        )
        for section in walk_sections(document)
        if len((section.number or "").split(".")) <= depth_limit
    )
    figure_entries = tuple(
        IndexEntry(
            number=block.display_number or str(block.number),
            title=block.caption,
            target_id=block.figure_id,
        )
        for _, block in _blocks_in_order(document)
        if isinstance(block, Figure)
    )
    table_entries = tuple(
        IndexEntry(
            number=block.display_number or str(block.number),
            title=block.caption,
            target_id=block.table_id,
        )
        for _, block in _blocks_in_order(document)
        if isinstance(block, Table) and block.caption
    )

    def fix(block):
        if isinstance(block, TableOfContents):
            return replace(block, entries=contents)
        if isinstance(block, ListOfFigures):
            return replace(block, entries=figure_entries)
        if isinstance(block, ListOfTables):
            return replace(block, entries=table_entries)
        return block

    return _map_blocks(document, fix)


def _map_blocks(document: Document, fix) -> Document:
    def rebuild(section: Section) -> Section:
        return replace(
            section,
            blocks=tuple(fix(block) for block in section.blocks),
            subsections=tuple(rebuild(child) for child in section.subsections),
        )

    return replace(
        document,
        front_matter=tuple(fix(block) for block in document.front_matter),
        sections=tuple(rebuild(section) for section in document.sections),
    )


def render_inline(run: Inline) -> str:
    """The text an exporter should print for one inline run.

    Shared so that DOCX and PDF cannot render the same cross-reference
    differently — the string is decided here, once.
    """
    if isinstance(run, Text):
        return run.value
    resolved = getattr(run, "resolved", None)
    if resolved is None:
        raise UnresolvedReference(f"{run.target_id!r} was never resolved; number() was not run")
    return resolved


def render_runs(runs) -> str:
    return "".join(render_inline(run) for run in runs)
