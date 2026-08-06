"""Extraction: normalised text in, a valid CPM or an honest refusal out.

The completeness floor (FR-5) is the load-bearing part. When a description does
not support a model, the run reports that and stops. It does not pad the model
to look finished — a fabricated entity set is worse than no output at all,
because the user cannot tell the difference and submits it (risk R1).
"""

import logging
from datetime import UTC, datetime

from cpm.schema import CPM, CPMCollections
from extraction.normalise import normalise
from extraction.result import Extracted, ExtractionResult, InsufficientInput
from llm.gateway import LLMGateway

logger = logging.getLogger(__name__)

MIN_ENTITIES = 3
MIN_RELATIONSHIPS = 2
"""Applied to every extraction regardless of input length. A short-but-concrete
description (few words, a clean 3+ entities and 2+ relationships) already
clears this on its own merits — length was never the thing worth gating on.
Gating the floor behind a word count let a description of any length under
the old threshold reach confirm with as few as one entity and zero
relationships, silently, with no guidance: exactly the thin, broken model
FR-5 exists to catch."""


class ExtractionService:
    def __init__(self, gateway: LLMGateway, task_name: str = "cpm_extraction") -> None:
        self._gateway = gateway
        self._task_name = task_name

    async def extract(
        self,
        text: str,
        *,
        project_name: str,
        authors: list[str] | None = None,
        created_at: datetime | None = None,
        user_id: str | None = None,
    ) -> ExtractionResult:
        normalised_text = " ".join(text.split())
        word_count = len(normalised_text.split())

        raw = await self._gateway.complete(
            self._task_name, normalised_text, CPMCollections, user_id=user_id
        )

        outcome = normalise(raw)
        collections = outcome.collections

        shortfall = _check_floor(collections, word_count)
        if shortfall is not None:
            logger.info(
                "extraction returned insufficient input: %d words, %d entities, %d relationships",
                word_count,
                shortfall.entities_found,
                shortfall.relationships_found,
            )
            return shortfall

        cpm = CPM.model_validate(
            {
                **collections.model_dump(by_alias=True),
                "meta": {
                    # Neither of these is the model's to guess at.
                    "projectName": project_name,
                    "authors": authors or [],
                    "createdAt": created_at or datetime.now(UTC),
                },
            }
        )
        return Extracted(cpm=cpm, notes=outcome.notes)


def _check_floor(collections: CPMCollections, word_count: int) -> InsufficientInput | None:
    entities = len(collections.entities)
    relationships = len(collections.relationships)

    if entities == 0:
        return InsufficientInput(
            reason=(
                "No entities could be identified in the description, so there is nothing "
                "to build a model from."
            ),
            word_count=word_count,
            entities_found=0,
            relationships_found=relationships,
            guidance=_guidance(collections),
        )

    if entities < MIN_ENTITIES or relationships < MIN_RELATIONSHIPS:
        return InsufficientInput(
            reason=(
                f"Only {entities} entit{'y' if entities == 1 else 'ies'} and "
                f"{relationships} relationship{'' if relationships == 1 else 's'} could be "
                f"identified from the description ({word_count} words). It describes intent "
                "rather than a system."
            ),
            word_count=word_count,
            entities_found=entities,
            relationships_found=relationships,
            guidance=_guidance(collections),
        )

    return None


def _guidance(collections: CPMCollections) -> list[str]:
    """Concrete additions, named. "Add more detail" helps nobody — and
    neither does a fixed library example when the description was never
    about a library. Someone whose idea does not already come pre-shaped as
    "entities and relationships" should not have to guess how to translate
    generic advice into their own words: where the description already named
    things, the guidance below asks about those things, by name, instead."""
    entities = collections.entities
    names = [entity.name for entity in entities]

    suggestions: list[str] = []

    if len(entities) < MIN_ENTITIES:
        suggestions.append(
            "Name the things the system stores or tracks, and what each one holds — "
            "for example: 'A book has an ISBN, a title and an author. A member has a "
            "membership number and a name.'"
        )
    if len(collections.relationships) < MIN_RELATIONSHIPS:
        if len(names) >= 2:
            suggestions.append(
                f"You named {_list(names)} — say how they connect. Pick two and "
                f"describe it in one sentence, the way you'd explain it to a person: "
                f"'A {names[0]} belongs to one {names[1]}', or 'A {names[0]} has many "
                f"{names[1]}.' Do that for every pair that actually relates — it does "
                f"not need to be every possible pair."
            )
        else:
            suggestions.append(
                "Say how those things relate to each other — for example: 'A member "
                "borrows many loans, and each loan is for one book.'"
            )
    suggestions.append(
        "Describe who uses the system and what each of them does — for example: "
        "'A librarian issues and accepts returns; an administrator manages members.'"
    )
    suggestions.append(
        "Describe what happens step by step for the main task, including what the "
        "system does at each step."
    )
    return suggestions


def _list(names: list[str], limit: int = 5) -> str:
    shown = names[:limit]
    rendered = shown[0] if len(shown) == 1 else f"{', '.join(shown[:-1])} and {shown[-1]}"
    if len(names) > limit:
        rendered += f", and {len(names) - limit} more"
    return rendered
