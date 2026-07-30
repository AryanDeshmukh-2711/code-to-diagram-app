"""What extraction returns.

Two outcomes, both legitimate. `InsufficientInput` is not an error — it is the
correct answer to a description that does not describe a system, and returning
it is what keeps risk R1 (a plausible-but-wrong artefact reaching a submission)
from starting here.
"""

from dataclasses import dataclass, field

from cpm.schema import CPM


@dataclass(frozen=True)
class Extracted:
    """A model was derived and passed every consistency check."""

    cpm: CPM
    notes: list[str] = field(default_factory=list)
    """What normalisation changed, in human terms.

    Surfaced at the review gate: a user cannot meaningfully confirm a model
    whose contents were silently edited on the way in.
    """


@dataclass(frozen=True)
class InsufficientInput:
    """The description does not support a model, and none was invented."""

    reason: str
    word_count: int
    entities_found: int
    relationships_found: int
    guidance: list[str] = field(default_factory=list)
    """Concrete things to add. "Insufficient input" alone leaves a user stuck."""


ExtractionResult = Extracted | InsufficientInput
