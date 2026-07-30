"""Failures a review edit can produce.

These are user-facing: every message is written to be shown in the UI next to
the field that caused it, not logged and swallowed.
"""


class ReviewError(Exception):
    """An edit that cannot be applied. The draft is left untouched."""


class UnknownElement(ReviewError):
    def __init__(self, kind: str, element_id: str) -> None:
        super().__init__(f"No {kind} with id {element_id!r} exists in this model.")


class NameCollision(ReviewError):
    """Two elements of the same kind would end up with the same identity.

    Refused rather than auto-suffixed. Silently producing "book-2" would leave
    the user with two boxes that look identical on the diagram and no idea why
    — and merging two concepts is a decision only they can make.
    """

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(
            f"Another {kind} is already called {name!r}. "
            "Rename or delete that one first, or pick a different name."
        )


class InvalidName(ReviewError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
