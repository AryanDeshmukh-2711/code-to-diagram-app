"""What each tier is allowed to do — configuration, read at call time.

FR-22. Every limit in the product lives in `tiers.json`, so raising the free
project cap from two to three is an edit to a file rather than a release. The
PRD's numbers are hypotheses; the margin query exists precisely because some
of them will turn out to be wrong, and a limit you cannot change without a
deploy is a hypothesis you cannot test.

`null` means unlimited, everywhere. It is spelt that way rather than as a
large number so that "unlimited" is unambiguous in the config a
non-programmer edits.
"""

import json
import os
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CONFIG_PATH = Path(os.getenv("ASA_TIERS_FILE", Path(__file__).resolve().parent / "tiers.json"))


class Tier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    monthly_price: Decimal
    rank: int = 0

    max_projects: int | None = None
    max_runs_per_month: int | None = None

    watermark: bool = False
    exports: tuple[str, ...] = ("pdf", "docx")
    diagram_formats: tuple[str, ...] = ("png", "svg")
    custom_template: bool = True
    templates: tuple[str, ...] = ()
    """Empty means every template. A named list restricts the tier to those."""

    queue: str = "default"
    upgrade_to: str | None = None

    def allows_template(self, template_id: str) -> bool:
        return not self.templates or template_id in self.templates

    def allows_export(self, fmt: str) -> bool:
        return fmt in self.exports

    def allows_diagram_format(self, fmt: str) -> bool:
        return fmt in self.diagram_formats


class TierBook(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    currency: str = "USD"
    tiers: tuple[Tier, ...] = Field(default_factory=tuple)

    def get(self, tier_id: str) -> Tier:
        for tier in self.tiers:
            if tier.id == tier_id:
                return tier
        raise UnknownTier(tier_id, [tier.id for tier in self.tiers])

    @property
    def default(self) -> Tier:
        return min(self.tiers, key=lambda tier: tier.rank)


class UnknownTier(KeyError):
    def __init__(self, tier_id: str, known: list[str]) -> None:
        super().__init__(f"no tier {tier_id!r}; configured tiers are {', '.join(known)}")


def load_tiers(path: Path | None = None) -> TierBook:
    """Read the tier configuration. Not cached, on purpose.

    A cached read would make "limits changeable without a deploy" false in the
    only way that matters: the process would keep serving yesterday's limits
    until someone restarted it, and nobody would know which was in force.
    """
    return TierBook.model_validate(json.loads((path or CONFIG_PATH).read_text(encoding="utf-8")))


def get_tier(tier_id: str) -> Tier:
    return load_tiers().get(tier_id)
