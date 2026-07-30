"""Pulling the names back out of generated diagram source.

Why extraction rather than a substring search: `"Book" in source` is **true**
when the source says `"Books"`. A substring check would pass the exact drift
FR-10 exists to catch, so names are extracted as delimited tokens and compared
whole.

Attribute lines are skipped deliberately. An attribute typed `string` would
otherwise be compared against an entity named `String` and reported as drift,
and a validator that cries wolf gets switched off.
"""

import re
from dataclasses import dataclass

from diagrams.types import Engine


@dataclass(frozen=True)
class ExtractedName:
    """One name-shaped token found in a diagram source."""

    text: str
    line: int
    context: str


_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
_PLANTUML_MEMBER = re.compile(r"^\s*[+\-#~]\s")
_PLANTUML_ARROW = re.compile(r"(-->|--\|>|\.\.\|>|\.\.>|\*--|o--|--|\.\.)")

_ER_ENTITY = re.compile(r'^\s*(?:"([^"]+)"|([A-Za-z][A-Za-z0-9_]*))\s*\{\s*$')
_ER_RELATION = re.compile(
    r'^\s*(?:"([^"]+)"|([A-Za-z][A-Za-z0-9_]*))'
    r"\s+[|}o][|o{]?[-.]{2}[|o][|{]?\s+"
    r'(?:"([^"]+)"|([A-Za-z][A-Za-z0-9_]*))'
    r"\s*:\s*(.*)$"
)


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _strip_quotes(text: str) -> str:
    trimmed = text.strip()
    if len(trimmed) >= 2 and trimmed[0] == '"' and trimmed[-1] == '"':
        return _unescape(trimmed[1:-1])
    return trimmed


def extract_plantuml(source: str) -> list[ExtractedName]:
    found: list[ExtractedName] = []

    for number, line in enumerate(source.splitlines(), start=1):
        if _PLANTUML_MEMBER.match(line):
            continue  # a class member, not a name

        context = line.strip()
        for match in _QUOTED.finditer(line):
            found.append(ExtractedName(_unescape(match.group(1)), number, context))

        # Relationship labels are unquoted, after " : " on an arrow line.
        if _PLANTUML_ARROW.search(line) and " : " in line:
            label = line.split(" : ", 1)[1].strip()
            if label:
                found.append(ExtractedName(_strip_quotes(label), number, context))

    return found


def extract_mermaid(source: str) -> list[ExtractedName]:
    found: list[ExtractedName] = []
    depth = 0

    for number, line in enumerate(source.splitlines(), start=1):
        context = line.strip()

        if depth > 0:
            # Inside an entity block: these are attributes, not names.
            depth -= line.count("}")
            continue

        entity = _ER_ENTITY.match(line)
        if entity:
            found.append(ExtractedName(entity.group(1) or entity.group(2), number, context))
            depth += 1
            continue

        relation = _ER_RELATION.match(line)
        if relation:
            left = relation.group(1) or relation.group(2)
            right = relation.group(3) or relation.group(4)
            label = _strip_quotes(relation.group(5))
            found.append(ExtractedName(left, number, context))
            found.append(ExtractedName(right, number, context))
            if label:
                found.append(ExtractedName(label, number, context))

    return found


_EXTRACTORS = {
    Engine.PLANTUML: extract_plantuml,
    Engine.MERMAID: extract_mermaid,
}


class UnsupportedSourceLanguage(RuntimeError):
    """No extractor for this engine.

    Raised rather than skipped: a diagram language the validator cannot read is
    a diagram the guarantee does not cover, and that has to be loud.
    """


def extract_names(source: str, engine: str) -> list[ExtractedName]:
    try:
        extractor = _EXTRACTORS[Engine(engine)]
    except (KeyError, ValueError):
        raise UnsupportedSourceLanguage(
            f"no name extractor for engine {engine!r}; FR-10 cannot be checked for it. "
            "Add one to shared/consistency/names.py before shipping this diagram type."
        ) from None
    return extractor(source)
