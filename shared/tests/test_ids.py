"""Id rules: url-safe slugs, and a stable derivation from a human name.

"Stable" is load-bearing. Ids appear in relationship.from/to, useCase.actors,
states.entityRef and nodes.deployedComponents. If slugify were not
deterministic, re-running extraction on the same input would silently
re-point every reference in the model.
"""

import pytest

from cpm.ids import MAX_SLUG_LENGTH, is_slug, slugify

VALID_SLUGS = [
    "book",
    "a",
    "book-1",
    "library-member",
    "isbn-13",
    "b" * MAX_SLUG_LENGTH,
]

INVALID_SLUGS = [
    "",
    " ",
    "-",
    "Book",  # uppercase
    "book_id",  # underscore
    "-book",  # leading separator
    "book-",  # trailing separator
    "book--id",  # doubled separator
    "bo ok",  # space
    "book/1",  # path separator
    "café",  # non-ascii
    "b" * (MAX_SLUG_LENGTH + 1),
]


@pytest.mark.parametrize("value", VALID_SLUGS)
def test_valid_slugs_are_accepted(value: str) -> None:
    assert is_slug(value)


@pytest.mark.parametrize("value", INVALID_SLUGS)
def test_invalid_slugs_are_rejected(value: str) -> None:
    assert not is_slug(value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Book", "book"),
        ("Library Member", "library-member"),
        ("  Book  ", "book"),
        ("Book--Copy", "book-copy"),
        ("Book_Id", "book-id"),
        ("ISBN13", "isbn13"),
        ("Loan #1", "loan-1"),
        ("a/b", "a-b"),
        ("Café Member", "cafe-member"),
        ("Über Book", "uber-book"),
    ],
)
def test_slugify_produces_expected_slug(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


@pytest.mark.parametrize("raw", ["Book", "Library Member", "Café Member", "Loan #1"])
def test_slugify_is_idempotent(raw: str) -> None:
    once = slugify(raw)
    assert slugify(once) == once


@pytest.mark.parametrize("raw", ["Book", "Library Member", "Fine Payment"])
def test_slugify_is_deterministic_across_calls(raw: str) -> None:
    assert len({slugify(raw) for _ in range(50)}) == 1


@pytest.mark.parametrize(
    "raw",
    ["Book", "Library Member", "Café Member", "Loan #1", "a" * 200, "Über--Book__Copy"],
)
def test_slugify_output_is_always_a_valid_slug(raw: str) -> None:
    assert is_slug(slugify(raw))


def test_slugify_truncates_without_leaving_a_trailing_separator() -> None:
    raw = " ".join(["word"] * 40)
    result = slugify(raw)
    assert len(result) <= MAX_SLUG_LENGTH
    assert is_slug(result)


@pytest.mark.parametrize("raw", ["", "   ", "!!!", "---", "。。"])
def test_slugify_refuses_input_with_no_slugifiable_characters(raw: str) -> None:
    # Returning "" would hand an invalid id to the caller; failing loudly keeps
    # the invariant that slugify's output is always a valid slug.
    with pytest.raises(ValueError):
        slugify(raw)
