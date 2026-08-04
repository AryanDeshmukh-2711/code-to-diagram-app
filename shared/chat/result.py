"""What parsing one chat message returns.

Three outcomes, all legitimate — mirrors `extraction.result`'s shape for the
same reason: a refusal to guess is not an error here either. `Clarify` and
`NotAnEdit` are the correct answers to an ambiguous or off-topic message, and
returning them is what keeps a misread chat message from silently mutating
someone's model (C-3, risk R1 arriving through natural language).
"""

from dataclasses import dataclass

from review import EditIn


@dataclass(frozen=True)
class ParsedEdit:
    """The message named one clear, in-scope operation."""

    edit: EditIn


@dataclass(frozen=True)
class Clarify:
    """The message could plausibly mean more than one thing."""

    question: str


@dataclass(frozen=True)
class NotAnEdit:
    """The message was not a request to change the model at all."""


ChatParseResult = ParsedEdit | Clarify | NotAnEdit
