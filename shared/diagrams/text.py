"""Shared text helpers for mappers.

Display names are emitted **verbatim** from the CPM. FR-10 requires every
entity and actor name in every artefact to be byte-identical to its name in the
model, so nothing here re-cases, abbreviates or pluralises a name. Only
characters that would break the diagram grammar are escaped, and identifiers
used purely as internal aliases are derived separately from the id.
"""

import re

_UNSAFE_ALIAS = re.compile(r"[^A-Za-z0-9_]")
_BARE_ER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_UNSAFE_ER_TOKEN = re.compile(r"[^A-Za-z0-9_]")


def alias(identifier: str) -> str:
    """An internal diagram alias derived from a CPM id.

    Hyphens are legal in CPM ids and are parsed as arrow fragments by PlantUML,
    so they become underscores. This never appears in the rendered output — the
    display name does — so FR-10 is unaffected.
    """
    return _UNSAFE_ALIAS.sub("_", identifier)


def quote(text: str) -> str:
    """A double-quoted literal for PlantUML, with the name left intact."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def er_name(name: str) -> str:
    """An entity name for Mermaid ER, quoted only when it has to be.

    Mermaid accepts a bare identifier or a quoted string. Names like "Parking
    Slot" need the quotes; "Book" does not. Either way the name itself is
    unchanged.
    """
    if _BARE_ER_NAME.match(name):
        return name
    return f'"{name.replace(chr(92), "").replace(chr(34), "")}"'


def er_token(text: str) -> str:
    """A single-token attribute type or name for Mermaid ER."""
    collapsed = _UNSAFE_ER_TOKEN.sub("_", text.strip())
    return collapsed or "unknown"
