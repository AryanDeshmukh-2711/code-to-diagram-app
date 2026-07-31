"""Enforcement, server-side, at the boundary.

Every check in this module runs inside the API process against the database.
None of it is advisory and none of it is duplicated in the browser: the UI may
grey out a button as a courtesy, but the button is not the lock. A quota
enforced in the front end is enforced against people who do not use the front
end, which is nobody worth stopping.

The messages are deliberately not punitive. A student who has hit the free
project limit at eleven at night has not done anything wrong, and telling them
so — plainly, with the number they hit and the way out — is both kinder and
better business than an error code. Every refusal carries what the limit was,
what they have used, and what the next tier gives them.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from billing.tiers import Tier, load_tiers
from store.models import AccountRow, GenerationRunRow, ProjectRow


@dataclass(frozen=True)
class QuotaRefusal:
    """A refusal a human can act on."""

    code: str
    message: str
    tier: str
    limit: int | str | None = None
    used: int | str | None = None
    upgrade_to: str | None = None
    upgrade_gives: str = ""

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "tier": self.tier,
            "limit": self.limit,
            "used": self.used,
            "upgradeTo": self.upgrade_to,
            "upgradeGives": self.upgrade_gives,
        }


class QuotaExceeded(Exception):
    """Raised by the enforcement service; turned into 402 at the boundary."""

    def __init__(self, refusal: QuotaRefusal) -> None:
        super().__init__(refusal.message)
        self.refusal = refusal


def _next_tier(tier: Tier) -> Tier | None:
    if tier.upgrade_to is None:
        return None
    try:
        return load_tiers().get(tier.upgrade_to)
    except KeyError:
        return None


def _upgrade_note(tier: Tier, about: str) -> tuple[str | None, str]:
    nxt = _next_tier(tier)
    if nxt is None:
        return None, ""
    offers = {
        "projects": (
            "unlimited projects" if nxt.max_projects is None else f"{nxt.max_projects} projects"
        ),
        "runs": (
            "unlimited runs"
            if nxt.max_runs_per_month is None
            else f"{nxt.max_runs_per_month} runs a month"
        ),
        "exports": f"{' and '.join(fmt.upper() for fmt in nxt.exports)} export",
        "diagram_formats": f"{', '.join(nxt.diagram_formats)} diagrams",
        "watermark": "documents without a watermark",
        "template": "any template, including your own",
    }
    return nxt.id, f"{nxt.name} (${nxt.monthly_price}/month) includes {offers.get(about, '')}"


async def account_tier(session, account_id: str) -> Tier:
    """The tier on record, or the cheapest configured one for a new account."""
    account = await session.get(AccountRow, account_id)
    book = load_tiers()
    if account is None:
        return book.default
    return book.get(account.tier)


async def check_new_project(session, account_id: str) -> Tier:
    tier = await account_tier(session, account_id)
    if tier.max_projects is None:
        return tier

    used = await session.scalar(
        select(func.count()).select_from(ProjectRow).where(ProjectRow.account_id == account_id)
    )
    if used >= tier.max_projects:
        upgrade, gives = _upgrade_note(tier, "projects")
        raise QuotaExceeded(
            QuotaRefusal(
                code="project_limit",
                message=(
                    f"You have {used} of {tier.max_projects} projects on the "
                    f"{tier.name} plan. Delete one you have finished with to start "
                    f"another, or move up a plan — everything you have made stays "
                    f"where it is."
                ),
                tier=tier.id,
                limit=tier.max_projects,
                used=used,
                upgrade_to=upgrade,
                upgrade_gives=gives,
            )
        )
    return tier


async def check_new_run(session, account_id: str, diagram_format: str) -> Tier:
    tier = await account_tier(session, account_id)

    if not tier.allows_diagram_format(diagram_format):
        upgrade, gives = _upgrade_note(tier, "diagram_formats")
        raise QuotaExceeded(
            QuotaRefusal(
                code="diagram_format",
                message=(
                    f"The {tier.name} plan renders diagrams as "
                    f"{' and '.join(tier.diagram_formats)}. Your documents will still "
                    f"contain every figure; {diagram_format.upper()} keeps them sharp at "
                    f"any zoom."
                ),
                tier=tier.id,
                limit=", ".join(tier.diagram_formats),
                used=diagram_format,
                upgrade_to=upgrade,
                upgrade_gives=gives,
            )
        )

    if tier.max_runs_per_month is not None:
        since = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = await session.scalar(
            select(func.count())
            .select_from(GenerationRunRow)
            .where(
                GenerationRunRow.account_id == account_id,
                GenerationRunRow.created_at >= since,
            )
        )
        if used >= tier.max_runs_per_month:
            upgrade, gives = _upgrade_note(tier, "runs")
            raise QuotaExceeded(
                QuotaRefusal(
                    code="run_limit",
                    message=(
                        f"You have generated {used} times this month, which is the "
                        f"{tier.name} allowance. It resets on the first of next month, "
                        f"and everything you have already generated stays available to "
                        f"download."
                    ),
                    tier=tier.id,
                    limit=tier.max_runs_per_month,
                    used=used,
                    upgrade_to=upgrade,
                    upgrade_gives=gives,
                )
            )
    return tier


async def check_export(session, account_id: str, fmt: str) -> Tier:
    tier = await account_tier(session, account_id)
    if tier.allows_export(fmt):
        return tier
    upgrade, gives = _upgrade_note(tier, "exports")
    raise QuotaExceeded(
        QuotaRefusal(
            code="export_format",
            message=(
                f"The {tier.name} plan exports "
                f"{' and '.join(f.upper() for f in tier.exports)}. Your document is "
                f"already generated — {fmt.upper()} export is the part that needs a "
                f"plan with it."
            ),
            tier=tier.id,
            limit=", ".join(tier.exports),
            used=fmt,
            upgrade_to=upgrade,
            upgrade_gives=gives,
        )
    )


async def check_template(session, account_id: str, template_id: str) -> Tier:
    tier = await account_tier(session, account_id)
    if tier.allows_template(template_id):
        return tier
    upgrade, gives = _upgrade_note(tier, "template")
    raise QuotaExceeded(
        QuotaRefusal(
            code="template_not_in_tier",
            message=(
                f"The {tier.name} plan uses the standard template. If your department "
                f"mandates a different one, that is what the next plan is for."
            ),
            tier=tier.id,
            limit=", ".join(tier.templates),
            used=template_id,
            upgrade_to=upgrade,
            upgrade_gives=gives,
        )
    )
