"""The engine contract.

An engine turns diagram source into bytes, and **fails loudly on invalid
source** rather than returning an image of an error message. That distinction
matters: a PlantUML server handed broken syntax will happily produce a
perfectly valid SVG whose content is the words "Syntax Error", and a caller
that only checks for bytes would embed that in a submitted document.
"""

from typing import Protocol

from diagrams.types import RenderFormat


class EngineError(RuntimeError):
    """The source could not be rendered. Never carries credentials."""


class EngineUnavailable(EngineError):
    """The engine could not be reached at all — distinct from bad syntax."""


class DiagramEngine(Protocol):
    name: str

    async def render(self, source: str, fmt: RenderFormat) -> bytes: ...
