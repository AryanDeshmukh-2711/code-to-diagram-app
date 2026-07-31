"""NFR-Q4: no unresolved placeholder may survive assembly.

The failure this stops is specific and embarrassing: a document that reaches a
supervisor with `{{project_name}}` in the header, or a caption reading
"Figure ?" because a cross-reference never resolved. Both are invisible in a
spot check of a forty-page PDF and fatal to the one thing the product sells —
a deliverable you can hand in without reading it first.

What counts as a placeholder is drawn narrowly and on purpose. Template markers
(`{{...}}`, `{%...%}`, `${...}`, `<<...>>`) are *ours*: if one survives, the
assembler failed. Unresolved cross-references are ours too. But "TBD" in a
requirement is the *user's* text — a student genuinely has undecided
requirements — and failing their document because they wrote TBD would be the
tool overruling its author. Those are returned as warnings, so the review
screen can surface them without the run dying.
"""

import re
from dataclasses import dataclass

from srs.ast import (
    BulletList,
    Document,
    FigureRef,
    NumberedList,
    Paragraph,
    SectionRef,
    TableRef,
    iter_strings,
    walk_blocks,
)

TEMPLATE_MARKER = re.compile(
    r"""
    \{\{.*?\}\}       # {{ handlebars }}
  | \{%.*?%\}         # {% jinja %}
  | \$\{[^}]*\}       # ${shell style}
  | <<[^<>\n]{1,80}>> # <<angle placeholder>>
  | \bFIGURE_NUMBER\b | \bSECTION_NUMBER\b
    """,
    re.VERBOSE,
)

SOFT_MARKER = re.compile(r"\b(?:TBD|TODO|FIXME|XXX|Lorem ipsum)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Placeholder:
    location: str
    token: str
    context: str

    def render(self) -> str:
        return f"  {self.location}: {self.token!r} in {self.context!r}"


class UnresolvedPlaceholder(RuntimeError):
    """Assembly produced a document that is not finished."""

    def __init__(self, found: list[Placeholder]) -> None:
        super().__init__(
            f"NFR-Q4: {len(found)} unresolved placeholder"
            f"{'' if len(found) == 1 else 's'} in the assembled document:\n"
            + "\n".join(item.render() for item in found)
        )
        self.found = found


def find_placeholders(document: Document) -> list[Placeholder]:
    found: list[Placeholder] = []

    for location, value in iter_strings(document):
        for match in TEMPLATE_MARKER.finditer(value):
            found.append(Placeholder(location, match.group(0), _context(value, match.start())))

    for section_id, block in walk_blocks(document):
        runs: tuple = ()
        if isinstance(block, Paragraph):
            runs = block.runs
        elif isinstance(block, BulletList | NumberedList):
            runs = tuple(run for item in block.items for run in item)
        for run in runs:
            if isinstance(run, FigureRef | TableRef | SectionRef) and run.resolved is None:
                found.append(
                    Placeholder(
                        section_id,
                        f"<unresolved reference to {run.target_id}>",
                        "cross-reference never numbered",
                    )
                )

    return found


def find_soft_markers(document: Document) -> list[Placeholder]:
    """TBD/TODO and friends. Reported, never fatal — see the module docstring."""
    return [
        Placeholder(location, match.group(0), _context(value, match.start()))
        for location, value in iter_strings(document)
        for match in SOFT_MARKER.finditer(value)
    ]


def assert_no_placeholders(document: Document) -> list[Placeholder]:
    """Raise if the document is unfinished; return the soft warnings.

    Called unconditionally at the end of assembly. There is no parameter to
    turn it off and none should be added: a placeholder check that can be
    skipped is a check that will be skipped on the night the deadline is
    closer than the bug.
    """
    found = find_placeholders(document)
    if found:
        raise UnresolvedPlaceholder(found)
    return find_soft_markers(document)


def _context(value: str, position: int) -> str:
    start = max(0, position - 30)
    end = min(len(value), position + 40)
    return ("…" if start else "") + value[start:end].strip() + ("…" if end < len(value) else "")
