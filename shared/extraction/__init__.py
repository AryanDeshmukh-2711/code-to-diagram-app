"""Extraction Service (SRS §3.1): normalised text -> Canonical Project Model.

Runs the LLM once, through the gateway, with the CPM collections schema as the
output contract. Everything after that is deterministic: merge duplicate names,
drop references that point at nothing, order every collection, then check the
completeness floor.

Nothing in the pipeline can add an element. That is what makes the floor mean
something — if normalisation could top up a thin model, the floor would only be
measuring its own output.
"""

from extraction.normalise import (
    NormalisationOutcome,
    canonical_name_key,
    normalise,
    normalise_display_name,
)
from extraction.result import Extracted, ExtractionResult, InsufficientInput
from extraction.service import (
    MIN_ENTITIES,
    MIN_RELATIONSHIPS,
    ExtractionService,
)

__all__ = [
    "MIN_ENTITIES",
    "MIN_RELATIONSHIPS",
    "Extracted",
    "ExtractionResult",
    "ExtractionService",
    "InsufficientInput",
    "NormalisationOutcome",
    "canonical_name_key",
    "normalise",
    "normalise_display_name",
]
