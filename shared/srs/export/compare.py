"""Comparing the text of two exported documents.

AT-1 claims the PDF and the DOCX say the same thing. This is the one place
that claim is checked, so that the acceptance test and the unit tests cannot
drift into two different definitions of "the same".

The comparison does not normalise the two streams until they match. It aligns
them and reports what differs, and the caller decides which differences are
legitimate. Three are, and only three:

* **List markers.** A bullet is paragraph formatting in DOCX and a drawn glyph
  in PDF. The DOCX text simply has no marker to extract.
* **Diagram text.** A vector figure keeps its own text — searchable, which is
  the reason to draw vector at all — so a PDF that embeds SVG contains every
  entity name inside the picture. The same figure as a raster in DOCX
  contributes nothing. The caller passes the vocabulary of the figures so
  those tokens are explained rather than waved through.
* **Page furniture.** Running heads and page numbers repeat per page in a
  paginated file and are stored once in DOCX.

Anything else — a missing sentence, a changed word, an invented heading — is a
real difference and is reported as one.
"""

import io
import re
from dataclasses import dataclass, field
from html import unescape

PAGE_NUMBER = re.compile(r"Page \d+ of \d+")
SVG_TEXT = re.compile(r"<(?:text|tspan)[^>]*>(.*?)</(?:text|tspan)>", re.S)
MARKERS = {"•", "\x7f", "-", "–", "‣", "◦"}


def is_list_marker(token: str) -> bool:
    return token in MARKERS or (token.isdigit() and len(token) <= 3)


@dataclass
class TextDifference:
    missing: list[str] = field(default_factory=list)
    """Words the DOCX has and the PDF does not. Always a failure."""

    markers: list[str] = field(default_factory=list)
    unexplained: list[str] = field(default_factory=list)
    """Extra words in the PDF that are neither markers nor figure text. Always
    a failure."""

    from_figures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.unexplained

    def render(self) -> str:
        if self.ok:
            return (
                f"identical apart from {len(self.markers)} list markers and "
                f"{len(self.from_figures)} words inside vector figures"
            )
        parts = []
        if self.missing:
            parts.append(f"{len(self.missing)} words missing from the PDF: {self.missing[:12]}")
        if self.unexplained:
            parts.append(
                f"{len(self.unexplained)} unexplained words in the PDF: {self.unexplained[:12]}"
            )
        return "; ".join(parts)


def docx_body_words(blob: bytes) -> list[str]:
    """Body text of a .docx from section 1 onward, tables included, in order."""
    from docx import Document as DocxDocument
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph as DocxParagraph

    document = DocxDocument(io.BytesIO(blob))
    chunks: list[str] = []
    started = False
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = DocxParagraph(child, document)
            if paragraph.style.name == "Heading 1" and paragraph.text.startswith("1 "):
                started = True
            if started and paragraph.text.strip():
                chunks.append(paragraph.text)
        elif child.tag.endswith("}tbl") and started:
            for row in DocxTable(child, document).rows:
                for cell in row.cells:
                    if cell.text.strip():
                        chunks.append(cell.text)
    return " ".join(chunks).split()


def pdf_body_words(blob: bytes, header: str) -> list[str]:
    """The same span of a PDF, with the page furniture removed.

    Where the body begins comes from the document's own outline, not from
    where a phrase first appears — the contents page names every heading too.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(blob))
    outline = [entry for entry in reader.outline if not isinstance(entry, list)]
    start = min(reader.get_destination_page_number(entry) for entry in outline) if outline else 0

    chunks: list[str] = []
    for page in reader.pages[start:]:
        for line in (page.extract_text() or "").splitlines():
            value = line.strip()
            if not value or value == header or PAGE_NUMBER.fullmatch(value):
                continue
            chunks.append(value)
    return " ".join(chunks).split()


def figure_vocabulary(sources: list[bytes | str]) -> set[str]:
    """Every word that appears inside the supplied SVG figures."""
    words: set[str] = set()
    for source in sources:
        text = source.decode("utf-8", "ignore") if isinstance(source, bytes) else source
        for fragment in SVG_TEXT.findall(text):
            cleaned = re.sub(r"<[^>]+>", " ", fragment)
            # Entities, because PlantUML writes a UML stereotype as
            # &#171;service&#187; in the SVG and the PDF draws it as
            # «service». Comparing the two forms would report every stereotype
            # in a component diagram as text the PDF invented.
            words.update(unescape(cleaned).split())
    return words


def compare(
    docx_words: list[str],
    pdf_words: list[str],
    figure_words: set[str] | None = None,
) -> TextDifference:
    """Align the two streams and classify every difference.

    Greedy subsequence matching rather than a diff: the question is whether
    everything the DOCX says appears in the PDF *in the same order*, and a diff
    algorithm confronted with a few hundred interleaved figure words starts
    reporting matching sentences as replacements. Greedy earliest-match answers
    the subsequence question exactly.
    """
    figure_words = figure_words or set()
    difference = TextDifference()

    index = 0
    for token in pdf_words:
        if index < len(docx_words) and token == docx_words[index]:
            index += 1
            continue
        if is_list_marker(token):
            difference.markers.append(token)
        elif token in figure_words:
            difference.from_figures.append(token)
        else:
            difference.unexplained.append(token)

    difference.missing = docx_words[index:]
    return difference
