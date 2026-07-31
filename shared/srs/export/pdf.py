"""PDF export — the same document, laid out on pages.

Built on ReportLab rather than an HTML engine, for three reasons that matter
here. It is pure Python, so the worker image needs no system libraries. It
draws SVG as real vector through svglib, so a diagram stays sharp at any zoom
and its text stays selectable and searchable — which for a marker skimming an
appendix is the difference between a figure and a picture of a figure. And it
gives access to the page canvas, which is what makes the free-tier watermark
(FR-20) a *render-time* mark: the watermark is drawn into each page's own
content stream as that page is produced. There is no second pass that reopens
a finished PDF and stamps something on top — no PDF is ever read back by this
module, which is asserted rather than promised.

AT-1 — identical content in both formats — is a property of the design, not a
diffing exercise. Both exporters are pure functions of the same `Document`,
and neither can add or drop a word the other does not have. The equivalence
test extracts the text of both files and compares it; it passes because
neither exporter has anywhere to get content from except the AST.
"""

import io
import logging
from dataclasses import dataclass

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Spacer,
    TableStyle,
)
from reportlab.platypus import (
    Paragraph as PdfParagraph,
)
from reportlab.platypus import (
    Table as PdfTable,
)
from reportlab.platypus.tableofcontents import TableOfContents as PdfTableOfContents

from srs.ast import (
    BulletList,
    Document,
    Figure,
    ListOfFigures,
    ListOfTables,
    NumberedList,
    Paragraph,
    Section,
    Table,
    TableOfContents,
)
from srs.export.template import A4, DocumentTemplate, Watermark
from srs.numbering import render_runs

logger = logging.getLogger(__name__)

VECTOR_FIRST = ("image/svg+xml", "image/png", "image/jpeg")
"""Preference order. Vector where possible, raster fallback — the requirement,
expressed as data."""

RASTER_DPI = 150.0
"""Assumed density for a raster fallback with no stated resolution. PlantUML's
PNG output is around this, and it keeps a full-width diagram legible in print
without inflating the file. Real DPI from the image metadata wins when present.
"""


class UnrenderableFigure(ValueError):
    """A figure in no format this exporter can draw."""


@dataclass(frozen=True)
class PdfResult:
    content: bytes
    figures: int
    tables: int
    sections: int
    vector_figures: int
    raster_figures: int

    @property
    def size(self) -> int:
        return len(self.content)


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------


class _Painter:
    """Draws everything that is not flowing content: the running head, the
    rule under it, and the watermark. Called by ReportLab once per page, while
    that page is being written."""

    def __init__(self, template: DocumentTemplate, project: str, watermark: Watermark | None):
        self.template = template
        self.project = project
        self.watermark = watermark

    def title_page(self, canvas, doc) -> None:
        # No running head on a title page; the watermark still applies.
        self._draw_watermark(canvas, doc)

    def body_page(self, canvas, doc) -> None:
        self._draw_watermark(canvas, doc)
        self._draw_header(canvas, doc)

    def _draw_header(self, canvas, doc) -> None:
        template = self.template
        text = template.header_text.format(project=self.project)
        y = (template.page_height_mm - template.margins.top_mm + 6) * mm

        canvas.saveState()
        canvas.setFont(_font(template.body_font), template.caption_size_pt)
        canvas.setFillColor(HexColor("#404040"))
        canvas.drawRightString((template.page_width_mm - template.margins.right_mm) * mm, y, text)
        if template.show_header_rule:
            canvas.setStrokeColor(HexColor("#A6A6A6"))
            canvas.setLineWidth(0.5)
            canvas.line(
                template.margins.left_mm * mm,
                y - 3,
                (template.page_width_mm - template.margins.right_mm) * mm,
                y - 3,
            )
        canvas.restoreState()

    def _draw_watermark(self, canvas, doc) -> None:
        """FR-20, drawn into this page's content stream as the page is made.

        Not an overlay merged into a finished document: by the time this
        function has run, the mark is part of the page, and there is no
        intermediate PDF anywhere that lacks it.
        """
        mark = self.watermark
        if mark is None:
            return

        template = self.template
        size = _watermark_size(mark, template)

        canvas.saveState()
        canvas.translate(
            template.page_width_mm * mm / 2,
            template.page_height_mm * mm / 2,
        )
        canvas.rotate(mark.angle)
        canvas.setFont(_font(mark.font), size)
        red, green, blue = mark.rgb
        canvas.setFillColor(Color(red, green, blue, alpha=mark.opacity))
        canvas.drawCentredString(0, 0, mark.text)
        if mark.subtext:
            canvas.setFont(_font(mark.font), size / 2.5)
            canvas.drawCentredString(0, -size, mark.subtext)
        canvas.restoreState()


def _watermark_size(mark: Watermark, template: DocumentTemplate) -> float:
    """Shrink the mark until it fits the page, never past it.

    A watermark clipped at both edges reads as a rendering bug rather than as a
    plan notice, and the text is not ours to shorten — it comes from the tier.
    """
    diagonal = ((template.page_width_mm * mm) ** 2 + (template.page_height_mm * mm) ** 2) ** 0.5
    usable = diagonal * 0.82
    width = pdfmetrics.stringWidth(mark.text, _font(mark.font), mark.size_pt)
    if width <= usable:
        return mark.size_pt
    return mark.size_pt * usable / width


def _footer_text(template: DocumentTemplate, page: int, total: int) -> str:
    return template.footer_text.format(page=page, pages=total)


def _numbered_canvas(template: DocumentTemplate, skip_first: bool):
    """A canvas that knows the page total before it writes the footers.

    "Page 3 of 19" cannot be drawn while page 3 is being laid out, because
    nothing knows yet how long the document is. ReportLab's answer, and the one
    used here: hold each page open until the document is finished, then write
    the footer into that page's own content stream. Still render time — the
    page is written once, with its footer — but with the total in hand.
    """
    from reportlab.pdfgen import canvas as pdf_canvas

    class NumberedCanvas(pdf_canvas.Canvas):
        """Holds pages open until the total is known, then writes each footer.

        Deferring showPage also defers everything else that is recorded against
        "the current page" — so bookmarks and outline entries are captured with
        the page they were made on and replayed at the right moment. Without
        that, every entry in the PDF's bookmark panel resolved to page 1: the
        outline looked complete and went nowhere.
        """

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages: list[dict] = []
            self._pending_marks: list[tuple[int, str]] = []
            self._pending_outline: list[tuple] = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def bookmarkPage(self, key, *args, **kwargs):
            self._pending_marks.append((len(self._pages), key))
            return key

        def addOutlineEntry(self, title, key, level=0, closed=None):
            self._pending_outline.append((title, key, level, closed))

        def save(self):
            total = len(self._pages)
            for index, state in enumerate(self._pages):
                self.__dict__.update(state)
                for page_index, key in self._pending_marks:
                    if page_index == index:
                        pdf_canvas.Canvas.bookmarkPage(self, key)
                if not (skip_first and index == 0):
                    self._footer(index + 1, total)
                pdf_canvas.Canvas.showPage(self)
            for title, key, level, closed in self._pending_outline:
                pdf_canvas.Canvas.addOutlineEntry(self, title, key, level, closed)
            pdf_canvas.Canvas.save(self)

        def _footer(self, page: int, total: int) -> None:
            self.saveState()
            self.setFont(_font(template.body_font), template.caption_size_pt)
            self.setFillColor(HexColor("#404040"))
            self.drawCentredString(
                template.page_width_mm * mm / 2,
                (template.margins.bottom_mm - 10) * mm,
                _footer_text(template, page, total),
            )
            self.restoreState()

    return NumberedCanvas


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_FONT_ALIASES = {
    "calibri": "Helvetica",
    "calibri light": "Helvetica",
    "arial": "Helvetica",
    "helvetica": "Helvetica",
    "times new roman": "Times-Roman",
    "times": "Times-Roman",
    "cambria": "Times-Roman",
    "georgia": "Times-Roman",
    "consolas": "Courier",
    "courier new": "Courier",
}


def _font(name: str) -> str:
    """Map a template's font onto one the PDF can actually set.

    ReportLab ships the fourteen standard PDF faces and nothing else. A
    template asking for Calibri gets the metrically closest standard face
    rather than a silent fallback to Helvetica with the wrong metrics — and
    registering the real TTF later changes only this function.
    """
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    return _FONT_ALIASES.get(name.strip().lower(), "Helvetica")


def _italic(font: str) -> str:
    return {
        "Helvetica": "Helvetica-Oblique",
        "Times-Roman": "Times-Italic",
        "Courier": "Courier-Oblique",
    }[_font(font)]


def _bold(font: str) -> str:
    return {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}[
        _font(font)
    ]


def _styles(template: DocumentTemplate) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body_font = _font(template.body_font)
    heading_font = _bold(template.heading_font)

    styles = {
        "Normal": ParagraphStyle(
            "ASA Normal",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=template.body_size_pt,
            leading=template.body_size_pt * template.line_spacing,
            spaceAfter=template.space_after_pt,
            alignment=base["BodyText"].alignment,
        ),
        "Caption": ParagraphStyle(
            "ASA Caption",
            parent=base["BodyText"],
            fontName=(
                _italic(template.caption_font)
                if template.caption_italic
                else _font(template.caption_font)
            ),
            fontSize=template.caption_size_pt,
            leading=template.caption_size_pt * 1.2,
            textColor=HexColor("#404040"),
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=12,
        ),
        "Title": ParagraphStyle(
            "ASA Title",
            parent=base["Title"],
            fontName=heading_font,
            fontSize=template.heading_size(1) * 1.6,
            leading=template.heading_size(1) * 2,
            textColor=HexColor(f"#{template.heading_colour}"),
        ),
        "Subtitle": ParagraphStyle(
            "ASA Subtitle",
            parent=base["Normal"],
            fontName=body_font,
            fontSize=template.body_size_pt * 1.2,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "Cell": ParagraphStyle(
            "ASA Cell",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=max(template.body_size_pt - 1.5, 7),
            leading=max(template.body_size_pt - 1.5, 7) * 1.2,
            spaceAfter=0,
        ),
    }
    for level in (1, 2, 3, 4):
        styles[f"Heading {level}"] = ParagraphStyle(
            f"ASA Heading {level}",
            parent=base["Heading1"],
            fontName=heading_font,
            fontSize=template.heading_size(level),
            leading=template.heading_size(level) * 1.2,
            textColor=HexColor(f"#{template.heading_colour}"),
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        )
    return styles


def _index_styles(template: DocumentTemplate) -> list[ParagraphStyle]:
    return [
        ParagraphStyle(
            f"ASA TOC {level}",
            fontName=_font(template.body_font),
            fontSize=template.body_size_pt,
            leading=template.body_size_pt * 1.4,
            leftIndent=12 * level,
            firstLineIndent=-12,
        )
        for level in range(3)
    ]


# ---------------------------------------------------------------------------
# Flowables
# ---------------------------------------------------------------------------


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _HeadingParagraph(PdfParagraph):
    """A heading that tells the contents page where it landed."""

    def __init__(self, text: str, style, level: int, key: str) -> None:
        super().__init__(text, style)
        self.entry_level = level
        self.entry_key = key
        self.entry_text = text


class _CaptionParagraph(PdfParagraph):
    """A caption that registers itself with the list of figures or tables."""

    def __init__(self, text: str, style, kind: str, key: str) -> None:
        super().__init__(text, style)
        self.entry_kind = kind
        self.entry_key = key
        self.entry_text = text


class _DocTemplate(BaseDocTemplate):
    """The document, plus the one hook that makes the indexes real.

    ReportLab notifies the template after each flowable is placed, which is the
    only moment at which "which page did this land on" has an answer. The
    contents page, the list of figures and the list of tables are all built
    from those notifications during a second layout pass, so their page numbers
    are measured rather than guessed — the same discipline as the AST's
    numbering, one level down.
    """

    def afterFlowable(self, flowable) -> None:
        if isinstance(flowable, _HeadingParagraph):
            self.canv.bookmarkPage(flowable.entry_key)
            self.canv.addOutlineEntry(
                flowable.entry_text, flowable.entry_key, level=flowable.entry_level
            )
            self.notify(
                "TOCEntry",
                (flowable.entry_level, flowable.entry_text, self.page, flowable.entry_key),
            )
        elif isinstance(flowable, _CaptionParagraph):
            self.canv.bookmarkPage(flowable.entry_key)
            self.notify(
                f"{flowable.entry_kind}Entry",
                (0, flowable.entry_text, self.page, flowable.entry_key),
            )


def _figure_flowable(block: Figure, template: DocumentTemplate, counters: dict) -> list:
    chosen = block.rendition(VECTOR_FIRST)
    if chosen is None:
        raise UnrenderableFigure(
            f"figure {block.figure_id!r} is only available as {block.mime!r}; "
            f"the PDF exporter can draw {', '.join(VECTOR_FIRST)}"
        )
    mime, payload = chosen
    available = template.content_width_mm * mm

    if mime == "image/svg+xml":
        drawing = _svg_drawing(payload)
        if drawing is not None:
            counters["vector"] += 1
            scale = min(1.0, available / drawing.width) if drawing.width else 1.0
            drawing.scale(scale, scale)
            drawing.width *= scale
            drawing.height *= scale
            drawing.hAlign = "CENTER"
            return [drawing]
        # Vector where possible — and where not, say so and use the raster.
        logger.warning("could not draw %s as vector; using the raster fallback", block.figure_id)
        fallback = block.rendition(("image/png", "image/jpeg"))
        if fallback is None:
            raise UnrenderableFigure(
                f"figure {block.figure_id!r} could not be drawn as vector and has no "
                f"raster fallback; render the run as PNG as well as SVG"
            )
        mime, payload = fallback

    counters["raster"] += 1
    return [_raster_image(payload, available)]


def _svg_drawing(payload: bytes):
    try:
        from svglib.svglib import svg2rlg

        return svg2rlg(io.BytesIO(payload))
    except Exception:  # pragma: no cover - depends on the SVG in hand
        logger.exception("svglib could not convert an SVG figure")
        return None


def _raster_image(payload: bytes, available: float) -> Image:
    """Place a bitmap at its true size, scaled down only if it overflows.

    Sizing from the image's own DPI rather than from its pixel count is what
    keeps a fallback legible: a 1600px diagram placed at 72dpi would be
    twenty-two inches wide and get scaled to a smear, while the same image read
    at its real density is a sharp 150dpi figure.
    """
    from PIL import Image as PilImage

    with PilImage.open(io.BytesIO(payload)) as probe:
        pixel_width, pixel_height = probe.size
        dpi_x, dpi_y = probe.info.get("dpi", (RASTER_DPI, RASTER_DPI))

    dpi_x = float(dpi_x) or RASTER_DPI
    dpi_y = float(dpi_y) or RASTER_DPI
    width = pixel_width / dpi_x * 72.0
    height = pixel_height / dpi_y * 72.0

    if width > available:
        height *= available / width
        width = available

    image = Image(io.BytesIO(payload), width=width, height=height)
    image.hAlign = "CENTER"
    return image


def _table_flowable(block: Table, template: DocumentTemplate, styles) -> PdfTable:
    header = [PdfParagraph(f"<b>{_escape(name)}</b>", styles["Cell"]) for name in block.columns]
    body = [[PdfParagraph(_escape(value), styles["Cell"]) for value in row] for row in block.rows]
    available = template.content_width_mm * mm
    table = PdfTable(
        [header, *body],
        colWidths=[available / len(block.columns)] * len(block.columns),
        repeatRows=1,
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#8F8F8F")),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#EDEDED")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


# ---------------------------------------------------------------------------
# The exporter
# ---------------------------------------------------------------------------


class _Index(PdfTableOfContents):
    """A contents list that listens for one kind of entry.

    ReportLab's own flowable only answers to "TOCEntry". The list of figures
    and the list of tables need their own channels, or all three would collect
    the same headings — which is exactly the sort of index that looks right in
    a screenshot and is wrong in the document.
    """

    def __init__(self, kind: str, styles) -> None:
        super().__init__()
        self._kind = f"{kind}Entry"
        self.levelStyles = styles

    def notify(self, kind, stuff):
        if kind == self._kind:
            self.addEntry(*stuff)


def _index_flowable(kind: str, template: DocumentTemplate):
    styles = _index_styles(template)
    return _Index(kind, styles if kind == "TOC" else styles[:1])


def export_pdf(
    source: Document,
    template: DocumentTemplate = A4,
    watermark: Watermark | None = None,
) -> PdfResult:
    """Render the document AST as a PDF.

    A pure function of the AST, the template and the watermark. It reads no
    database, calls no model, produces no intermediate DOCX, and never reopens
    the bytes it has written.
    """
    if not source.numbered:
        raise ValueError(
            "the document has not been numbered; export renders what assembly "
            "decided and must not assign numbers of its own"
        )

    styles = _styles(template)
    counters = {"vector": 0, "raster": 0}
    buffer = io.BytesIO()

    page_size = (template.page_width_mm * mm, template.page_height_mm * mm)
    doc = _DocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=template.margins.left_mm * mm,
        rightMargin=template.margins.right_mm * mm,
        topMargin=template.margins.top_mm * mm,
        bottomMargin=template.margins.bottom_mm * mm,
        title=source.title,
        author=", ".join(source.meta.authors) or None,
        subject=f"IEEE 830 Software Requirements Specification for {source.meta.project_name}",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body", showBoundary=0
    )
    painter = _Painter(template, source.meta.project_name, watermark)
    doc.addPageTemplates(
        [
            PageTemplate(id="title", frames=[frame], onPage=painter.title_page),
            PageTemplate(id="body", frames=[frame], onPage=painter.body_page),
        ]
    )

    story: list = []
    if template.title_page:
        story.append(NextPageTemplate("body"))
        story.append(Spacer(1, 60 * mm))
        story.append(PdfParagraph(_escape(source.title), styles["Title"]))
        story.append(Spacer(1, 8 * mm))
        story.append(PdfParagraph(f"Version {_escape(source.meta.version)}", styles["Subtitle"]))
        if source.meta.authors:
            story.append(PdfParagraph(_escape(", ".join(source.meta.authors)), styles["Subtitle"]))
        if source.meta.created_at:
            story.append(PdfParagraph(_escape(source.meta.created_at[:10]), styles["Subtitle"]))
        story.append(PageBreak())

    for block in source.front_matter:
        _append_block(story, block, template, styles, counters)

    if source.front_matter and source.sections:
        # Section 1 starts on a fresh page, as it does in the DOCX. The two
        # deliverables are the same document; a reader comparing them should
        # not find the body starting in a different place.
        story.append(PageBreak())

    for section in source.sections:
        _append_section(story, section, template, styles, counters, level=1)

    doc.multiBuild(story, canvasmaker=_numbered_canvas(template, template.title_page))

    from srs.ast import figures as ast_figures
    from srs.ast import tables as ast_tables
    from srs.ast import walk_sections

    return PdfResult(
        content=buffer.getvalue(),
        figures=len(ast_figures(source)),
        tables=len(ast_tables(source)),
        sections=len(list(walk_sections(source))),
        vector_figures=counters["vector"],
        raster_figures=counters["raster"],
    )


def _append_section(story, section: Section, template, styles, counters, level: int) -> None:
    story.append(
        _HeadingParagraph(
            _escape(f"{section.number} {section.title}"),
            styles[f"Heading {min(level, 4)}"],
            level=min(level, 3) - 1,
            key=f"sec-{section.section_id}",
        )
    )
    for block in section.blocks:
        _append_block(story, block, template, styles, counters)
    for child in section.subsections:
        _append_section(story, child, template, styles, counters, level + 1)


def _append_block(story, block, template, styles, counters) -> None:
    if isinstance(block, Paragraph):
        story.append(PdfParagraph(_escape(render_runs(block.runs)), styles["Normal"]))
    elif isinstance(block, BulletList | NumberedList):
        story.append(
            ListFlowable(
                [
                    ListItem(PdfParagraph(_escape(render_runs(item)), styles["Normal"]))
                    for item in block.items
                ],
                bulletType="bullet" if isinstance(block, BulletList) else "1",
                leftIndent=18,
                bulletFontName=_font(template.body_font),
            )
        )
    elif isinstance(block, Figure):
        # The caption stays a top-level flowable: ReportLab notifies the
        # document about what it places, and a caption buried inside a
        # container would never reach the list of figures. The image is wrapped
        # instead, and marked keepWithNext so the two never split across a page
        # break — a figure on one page and "Figure 3:" alone on the next is the
        # classic generated-document tell.
        image = KeepTogether(_figure_flowable(block, template, counters))
        image.keepWithNext = True
        story.append(image)
        story.append(
            _CaptionParagraph(
                _escape(f"{block.label}: {block.caption}"),
                styles["Caption"],
                kind="Figure",
                key=f"fig-{block.figure_id}",
            )
        )
    elif isinstance(block, Table):
        # Caption above the table, per convention, and pinned to it — a caption
        # stranded at the foot of the previous page is the same defect as an
        # orphaned figure caption.
        caption = _CaptionParagraph(
            _escape(f"{block.label}: {block.caption}"),
            styles["Caption"],
            kind="Table",
            key=f"tbl-{block.table_id}",
        )
        caption.keepWithNext = True
        story.append(caption)
        story.append(_table_flowable(block, template, styles))
        story.append(Spacer(1, 6 * mm))
    elif isinstance(block, TableOfContents | ListOfFigures | ListOfTables):
        title, kind = {
            TableOfContents: ("Contents", "TOC"),
            ListOfFigures: ("List of Figures", "Figure"),
            ListOfTables: ("List of Tables", "Table"),
        }[type(block)]
        story.append(PdfParagraph(title, styles["Heading 1"]))
        story.append(_index_flowable(kind, template))
        story.append(Spacer(1, 4 * mm))
