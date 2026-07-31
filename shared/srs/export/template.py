"""Page setup, fonts and running text — configuration, not code.

Every number an exporter needs to lay out a page lives here, in plain data, so
that "my university wants Times New Roman 12pt on A4 with 1 inch margins and
the course code in the header" is a row in a table rather than a patch to the
exporter. That is the whole reason this is a dataclass with a `from_dict`
rather than constants in the DOCX module: the template is the thing that
varies per user, and the exporter is the thing that does not.

Shared by every exporter on purpose. If DOCX and PDF each carried their own
idea of the margins, a student comparing the two would find them different
documents — which is exactly the failure the AST layer exists to prevent, one
level down.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Margins:
    top_mm: float = 25.4
    bottom_mm: float = 25.4
    left_mm: float = 25.4
    right_mm: float = 25.4


@dataclass(frozen=True)
class DocumentTemplate:
    """The resolved view an exporter reads.

    Built either from a preset or from a configured `Template`. The exporters
    only ever see this, so a template loaded from JSON and a template written
    in Python reach them by the same road.
    """

    name: str = "A4 default"

    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    margins: Margins = field(default_factory=Margins)

    body_font: str = "Calibri"
    body_size_pt: float = 11.0
    line_spacing: float = 1.15
    space_after_pt: float = 8.0

    heading_font: str = "Calibri Light"
    heading_sizes_pt: tuple[float, float, float] = (16.0, 14.0, 12.0)
    heading_colour: str = "1F3864"

    caption_font: str = "Calibri"
    caption_size_pt: float = 9.0
    caption_italic: bool = True

    monospace_font: str = "Consolas"
    table_style: str = "Table Grid"

    header_text: str = "{project}"
    footer_text: str = "Page {page} of {pages}"
    show_header_rule: bool = True

    title_page: bool = True

    styles: Mapping[str, Any] = field(default_factory=dict)
    """Named styles from a configured template, keyed by the names blocks use
    (`body`, `heading1`, `cover_title`, ...). Empty for the presets, which
    answer style questions from their own fields."""

    def resolved(self, name: str):
        """The style a block asked for, or None to fall back to the preset."""
        return self.styles.get(name)

    @property
    def content_width_mm(self) -> float:
        return self.page_width_mm - self.margins.left_mm - self.margins.right_mm

    def heading_size(self, level: int) -> float:
        """Levels below the configured three inherit the smallest size rather
        than shrinking without limit — a 4pt heading is not a heading."""
        index = min(max(level, 1), len(self.heading_sizes_pt)) - 1
        return self.heading_sizes_pt[index]

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "DocumentTemplate":
        """Build from stored configuration, ignoring nothing silently."""
        payload = dict(values)
        margins = payload.pop("margins", None)
        unknown = set(payload) - {f.name for f in cls.__dataclass_fields__.values()}
        if unknown:
            # A misspelt key that is quietly dropped becomes "the template did
            # not apply and nobody knows why" three weeks before a deadline.
            raise ValueError(f"unknown template settings: {', '.join(sorted(unknown))}")
        if "heading_sizes_pt" in payload:
            payload["heading_sizes_pt"] = tuple(payload["heading_sizes_pt"])
        template = cls(**payload)
        if margins is not None:
            template = replace(template, margins=Margins(**margins))
        return template


@dataclass(frozen=True)
class Watermark:
    """FR-20: the mark a free-tier document carries.

    Data, not behaviour, so the exporter cannot decide on its own whether to
    apply one — the plan decides, and the exporter draws what it is given.
    """

    text: str
    subtext: str = ""
    angle: float = 45.0
    size_pt: float = 46.0
    opacity: float = 0.12
    rgb: tuple[float, float, float] = (0.45, 0.45, 0.55)
    font: str = "Calibri"


FREE_TIER = Watermark(
    text="AI Software Architect — Free plan",
    subtext="Upgrade to remove this watermark",
)
"""Legible enough to be a real mark and light enough that the document under it
stays readable. A watermark nobody can read past is a broken deliverable, and a
watermark nobody notices is not a watermark."""


A4 = DocumentTemplate()

US_LETTER = replace(
    DocumentTemplate(),
    name="US Letter default",
    page_width_mm=215.9,
    page_height_mm=279.4,
)

IEEE_TIMES = replace(
    DocumentTemplate(),
    name="Times New Roman 12pt, A4",
    body_font="Times New Roman",
    body_size_pt=12.0,
    heading_font="Times New Roman",
    heading_sizes_pt=(16.0, 14.0, 12.0),
    heading_colour="000000",
    caption_font="Times New Roman",
    caption_size_pt=10.0,
    line_spacing=1.5,
)
"""The one most university templates actually ask for."""

TEMPLATES = {
    "a4": A4,
    "letter": US_LETTER,
    "ieee-times": IEEE_TIMES,
}


def get_template(name: str | None) -> DocumentTemplate:
    if name is None:
        return A4
    try:
        return TEMPLATES[name]
    except KeyError:
        raise ValueError(
            f"unknown template {name!r}; known templates: {', '.join(sorted(TEMPLATES))}"
        ) from None
