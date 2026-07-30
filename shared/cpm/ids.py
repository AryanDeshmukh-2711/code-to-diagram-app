"""Stable, url-safe identifiers for CPM elements.

Ids are the glue of the whole model: relationship.from/to, useCase.actors,
states.entityRef and nodes.deployedComponents are all id references. Two
properties matter and are tested:

* **url-safe** — lowercase ascii words joined by single hyphens, so an id can
  sit in a URL, a filename, a PlantUML alias and a DOM id without escaping.
* **stable** — slugify is a pure, deterministic, idempotent function of the
  name. Re-running extraction over the same input yields the same ids, so
  references stay pointing where they did.
"""

import re
import unicodedata
from typing import Annotated

from pydantic import StringConstraints

MAX_SLUG_LENGTH = 64

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

_SLUG_RE = re.compile(SLUG_PATTERN)
_SEPARATOR_RUN_RE = re.compile(r"[^a-z0-9]+")

Slug = Annotated[
    str,
    StringConstraints(pattern=SLUG_PATTERN, min_length=1, max_length=MAX_SLUG_LENGTH),
]
"""An id. Deliberately does NOT strip whitespace — " book" is a malformed id,
not an id that needs tidying, and hiding that would mask a broken extractor."""


def is_slug(value: str) -> bool:
    """True when value is already a valid, length-bounded slug."""
    return len(value) <= MAX_SLUG_LENGTH and _SLUG_RE.match(value) is not None


def slugify(value: str, *, max_length: int = MAX_SLUG_LENGTH) -> str:
    """Derive a slug from a human-readable name.

    Deterministic and idempotent: ``slugify(slugify(x)) == slugify(x)``.

    Raises:
        ValueError: if nothing slugifiable remains. Returning "" would hand an
            invalid id to the caller and break the invariant that this
            function's output always satisfies :func:`is_slug`.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    collapsed = _SEPARATOR_RUN_RE.sub("-", ascii_only.lower()).strip("-")

    if len(collapsed) > max_length:
        collapsed = collapsed[:max_length].rstrip("-")

    if not collapsed:
        raise ValueError(f"cannot derive a url-safe slug from {value!r}")

    return collapsed
