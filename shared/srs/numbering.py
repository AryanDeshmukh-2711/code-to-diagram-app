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

from dataclasses import replace

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


class UnresolvedReference(LookupError):
    """A cross-reference pointing at something the document does not contain.

    Loud rather than silent: a dangling reference rendered as "see Figure ?"
    is exactly the kind of blemish that gets a submission handed back, and it
    is invisible in a spot check of a forty-page document.
    """


def number(document: Document) -> Document:
    """Assign every number in the document and resolve every reference."""
    sections = _number_sections(document.sections)
    numbered = replace(document, sections=sections)

    figure_numbers, table_numbers = _assign_captioned(numbered)
    numbered = _apply_captions(numbered, figure_numbers, table_numbers)

    section_numbers = {s.section_id: (s.number or "", s.title) for s in walk_sections(numbered)}
    numbered = _resolve_references(numbered, figure_numbers, table_numbers, section_numbers)
    numbered = _fill_indexes(numbered)

    return replace(numbered, numbered=True)


# ---------------------------------------------------------------------------


def _number_sections(sections: tuple[Section, ...], prefix: str = "") -> tuple[Section, ...]:
    out = []
    for index, section in enumerate(sections, start=1):
        label = f"{prefix}{index}" if not prefix else f"{prefix}.{index}"
        out.append(
            replace(
                section,
                number=label,
                subsections=_number_sections(section.subsections, label),
            )
        )
    return tuple(out)


def _assign_captioned(document: Document) -> tuple[dict[str, int], dict[str, int]]:
    """Walk in reading order and hand out figure and table numbers.

    Sequential across the whole document, not restarted per chapter: "Figure 7"
    is unambiguous when a marker is looking for the seventh figure, and per-
    chapter numbering is where off-by-one errors hide.
    """
    figure_numbers: dict[str, int] = {}
    table_numbers: dict[str, int] = {}

    for _, block in _blocks_in_order(document):
        if isinstance(block, Figure) and block.figure_id not in figure_numbers:
            figure_numbers[block.figure_id] = len(figure_numbers) + 1
        elif isinstance(block, Table) and block.table_id not in table_numbers:
            table_numbers[block.table_id] = len(table_numbers) + 1

    return figure_numbers, table_numbers


def _blocks_in_order(document: Document):
    for block in document.front_matter:
        yield "<front>", block

    def descend(section: Section):
        for block in section.blocks:
            yield section.section_id, block
        for child in section.subsections:
            yield from descend(child)

    for section in document.sections:
        yield from descend(section)


def _apply_captions(
    document: Document, figure_numbers: dict[str, int], table_numbers: dict[str, int]
) -> Document:
    def fix(block):
        if isinstance(block, Figure):
            return replace(block, number=figure_numbers.get(block.figure_id))
        if isinstance(block, Table):
            return replace(block, number=table_numbers.get(block.table_id))
        return block

    return _map_blocks(document, fix)


def _resolve_references(
    document: Document,
    figure_numbers: dict[str, int],
    table_numbers: dict[str, int],
    section_numbers: dict[str, tuple[str, str]],
) -> Document:
    missing: list[str] = []

    def resolve(run: Inline) -> Inline:
        if isinstance(run, FigureRef):
            found = figure_numbers.get(run.target_id)
            if found is None:
                missing.append(f"figure {run.target_id!r}")
                return run
            return replace(run, resolved=f"Figure {found}")
        if isinstance(run, TableRef):
            found = table_numbers.get(run.target_id)
            if found is None:
                missing.append(f"table {run.target_id!r}")
                return run
            return replace(run, resolved=f"Table {found}")
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
    contents = tuple(
        IndexEntry(
            number=section.number or "",
            title=section.title,
            target_id=section.section_id,
            depth=len((section.number or "").split(".")),
        )
        for section in walk_sections(document)
    )
    figure_entries = tuple(
        IndexEntry(number=str(block.number), title=block.caption, target_id=block.figure_id)
        for _, block in _blocks_in_order(document)
        if isinstance(block, Figure)
    )
    table_entries = tuple(
        IndexEntry(number=str(block.number), title=block.caption, target_id=block.table_id)
        for _, block in _blocks_in_order(document)
        if isinstance(block, Table)
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
