"""Telling "extraction was excellent" apart from "they didn't look".

Both produce a confirmation with zero edits, and they demand opposite
responses: one says ship it, the other says the review gate is decorative and
the product's whole differentiator is a lie. A metric that reports "68% of
users confirm without editing" and stops there is worse than no metric,
because it reads as good news either way.

The edit count cannot separate them. Nothing about the *outcome* can — the
outcome is identical. What separates them is evidence of attention, which has
to be collected while the user is on the screen and shipped with the
confirmation:

    dwell        how long the screen was open, and how much of that was active
    coverage     how many of the model's items were actually brought into view
    inspections  expanding, focusing, opening a picker — looking without changing

A confirmation with zero edits, four minutes of active time and every entity
viewed is a person who checked. A confirmation with zero edits, nine seconds
and two of twenty-two items viewed is a person who clicked past a gate. The
first is a compliment to the extractor; the second is a product problem.

The thresholds below are hypotheses, and they are the kind that has to be
validated against real users watching real screens — which is what P-M0-1's
interviews were for. They are configurable for that reason, and the dashboard
shows the raw signals beside the verdict so the verdict can be argued with.
"""

from dataclasses import dataclass, field
from typing import Any

BASE_SECONDS = 8.0
"""Time to orient on the screen at all, before looking at any one item."""

SECONDS_PER_ITEM = 1.6
"""How long a glance at one entity or use case plausibly takes. Deliberately
low: this is the floor of "looked at it", not the average of a careful read."""

COVERAGE_FLOOR = 0.6
ATTENTION_FLOOR = 0.5

EDITED = "edited"
VERIFIED = "verified"
RUBBER_STAMPED = "rubber_stamped"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReviewSignals:
    """What the review screen observed, sent with the confirmation."""

    edits_total: int = 0
    edits_by_op: dict[str, int] = field(default_factory=dict)
    edits_reverted: int = 0

    seconds_on_screen: float = 0.0
    active_seconds: float = 0.0
    """Excludes idle: a screen left open over lunch is not four minutes of
    review, and counting it that way would let inattention look like care."""

    items_total: int = 0
    items_viewed: int = 0
    sections_viewed: tuple[str, ...] = ()
    inspections: int = 0

    issues_at_open: int = 0
    issues_at_confirm: int = 0

    @property
    def coverage(self) -> float:
        return self.items_viewed / self.items_total if self.items_total else 0.0

    @property
    def expected_seconds(self) -> float:
        """How long looking at this model would plausibly take.

        Scaled by size, because twenty seconds is attentive for a three-entity
        model and derisory for a forty-entity one. A fixed threshold would
        flatter big models and punish small ones.
        """
        return BASE_SECONDS + SECONDS_PER_ITEM * self.items_total

    @property
    def attention_ratio(self) -> float:
        return self.active_seconds / self.expected_seconds if self.expected_seconds else 0.0

    @property
    def verdict(self) -> str:
        if self.edits_total > 0:
            return EDITED
        if self.items_total == 0 or self.active_seconds <= 0:
            # The screen sent no signals at all. Reported as its own bucket
            # rather than folded into either answer — an unmeasured
            # confirmation is not evidence for anything.
            return UNKNOWN
        if self.coverage >= COVERAGE_FLOOR and self.attention_ratio >= ATTENTION_FLOOR:
            return VERIFIED
        return RUBBER_STAMPED

    def as_payload(self) -> dict[str, Any]:
        """The event body. Raw signals *and* the verdict.

        Both, on purpose: storing only the verdict would make the thresholds
        unarguable after the fact, and re-classifying six months of history
        against a better threshold is exactly what will be wanted once the
        interviews happen.
        """
        return {
            "editsTotal": self.edits_total,
            "editsByOp": dict(self.edits_by_op),
            "editsReverted": self.edits_reverted,
            "secondsOnScreen": round(self.seconds_on_screen, 1),
            "activeSeconds": round(self.active_seconds, 1),
            "itemsTotal": self.items_total,
            "itemsViewed": self.items_viewed,
            "sectionsViewed": list(self.sections_viewed),
            "inspections": self.inspections,
            "issuesAtOpen": self.issues_at_open,
            "issuesAtConfirm": self.issues_at_confirm,
            "coverage": round(self.coverage, 3),
            "expectedSeconds": round(self.expected_seconds, 1),
            "attentionRatio": round(self.attention_ratio, 3),
            "verdict": self.verdict,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ReviewSignals":
        return cls(
            edits_total=payload.get("editsTotal", 0),
            edits_by_op=payload.get("editsByOp", {}) or {},
            edits_reverted=payload.get("editsReverted", 0),
            seconds_on_screen=payload.get("secondsOnScreen", 0.0),
            active_seconds=payload.get("activeSeconds", 0.0),
            items_total=payload.get("itemsTotal", 0),
            items_viewed=payload.get("itemsViewed", 0),
            sections_viewed=tuple(payload.get("sectionsViewed", ())),
            inspections=payload.get("inspections", 0),
            issues_at_open=payload.get("issuesAtOpen", 0),
            issues_at_confirm=payload.get("issuesAtConfirm", 0),
        )


def interpret(verdict: str) -> str:
    """What each bucket means for what to do next."""
    return {
        EDITED: "the gate did work: the model was wrong and the user fixed it",
        VERIFIED: "zero edits after real inspection — evidence the extractor is good",
        RUBBER_STAMPED: "zero edits without inspection — the gate is decorative",
        UNKNOWN: "the screen sent no attention signals; not evidence either way",
    }[verdict]
