"""Pulling text out of an uploaded PDF, in two deliberately separate steps.

**Probing is cheap and happens in the request.** Reading a PDF's page count
touches its cross-reference table, not its content streams — it is fast
regardless of what is inside each page, so it can reject an oversized or
unreadable upload synchronously, with a specific reason, before anything is
queued.

**Extracting text is not cheap, and never runs in the request cycle (C-4).**
`.extract_text()` walks every content stream on every page, and a small file
with pathologically nested or malformed content can make that slow even when
its byte size and page count both look innocent. The page/size ceiling in
`probe_pdf` is the fast, cheap defence; running the actual extraction only in
the worker — bounded by arq's own job timeout — is the defence against the
input that gets past the cheap checks and turns out to be slow anyway. A
single untrusted upload should never be able to occupy an HTTP worker thread
for an unbounded amount of time.
"""

import io
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_BYTES = 15 * 1024 * 1024
"""Generous for a text-heavy project description or report; well short of
anything that turns page-by-page extraction into a real resource cost."""

MAX_PDF_PAGES = 60
"""A project description or an SRS-length document is nowhere near this. A
scanned book is exactly what this exists to reject before it is queued."""


class PdfRejected(ValueError):
    """The upload was refused before any extraction was attempted.

    A ValueError, not something extraction-specific: this can be raised from
    the HTTP request, synchronously, and turned straight into a 400 with the
    message as the reason.
    """


@dataclass(frozen=True)
class PdfProbe:
    pages: int


def probe_pdf(data: bytes) -> PdfProbe:
    """Cheap, synchronous checks: size, then page count. Safe to call from a
    request handler — nothing here reads the text of a single page."""
    if len(data) > MAX_PDF_BYTES:
        raise PdfRejected(
            f"that PDF is {len(data) / 1_048_576:.1f}MB; the limit is "
            f"{MAX_PDF_BYTES / 1_048_576:.0f}MB. Split it or paste the "
            f"description as text instead."
        )
    try:
        reader = _reader(data)
        pages = len(reader.pages)
    except PdfReadError as exc:
        raise PdfRejected(f"that file could not be read as a PDF: {exc}") from exc
    except Exception as exc:  # pragma: no cover - pypdf's own edge cases
        raise PdfRejected(f"that file could not be read as a PDF: {exc}") from exc

    if pages > MAX_PDF_PAGES:
        raise PdfRejected(
            f"that PDF has {pages} pages; the limit is {MAX_PDF_PAGES}. A "
            f"project description or report should be well under that — "
            f"trim it or paste the relevant text instead."
        )
    if pages == 0:
        raise PdfRejected("that PDF has no pages.")
    return PdfProbe(pages=pages)


def extract_pdf_text(data: bytes) -> str:
    """The actual per-page extraction. Worker-only — never call this from a
    request handler; call `probe_pdf` there instead."""
    reader = _reader(data)
    pieces = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(piece for piece in pieces if piece.strip())


def _reader(data: bytes) -> PdfReader:
    return PdfReader(io.BytesIO(data))
