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

FLOOR_WORD_COUNT = 200
"""FR-5 applies to inputs of at least this many words. Below it, a terse but
concrete description is accepted — over-rejecting a real system described in
few words would be its own failure."""

MIN_ENTITIES = 3
MIN_RELATIONSHIPS = 2


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
            guidance=_guidance(entities, relationships),
        )

    if word_count >= FLOOR_WORD_COUNT and (
        entities < MIN_ENTITIES or relationships < MIN_RELATIONSHIPS
    ):
        return InsufficientInput(
            reason=(
                f"The description is {word_count} words long but only {entities} "
                f"entit{'y' if entities == 1 else 'ies'} and {relationships} "
                f"relationship{'' if relationships == 1 else 's'} could be identified. "
                "It describes intent rather than a system."
            ),
            word_count=word_count,
            entities_found=entities,
            relationships_found=relationships,
            guidance=_guidance(entities, relationships),
        )

    return None


def _guidance(entities: int, relationships: int) -> list[str]:
    """Concrete additions, named. "Add more detail" helps nobody."""
    suggestions: list[str] = []

    if entities < MIN_ENTITIES:
        suggestions.append(
            "Name the things the system stores or tracks, and what each one holds — "
            "for example: 'A book has an ISBN, a title and an author. A member has a "
            "membership number and a name.'"
        )
    if relationships < MIN_RELATIONSHIPS:
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
